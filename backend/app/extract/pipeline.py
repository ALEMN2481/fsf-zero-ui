"""Correo guardado → movimiento en transactions (Paso 09B).

Doble conteo factura/banco (regla del supervisor, en los dos órdenes de llegada):
- La factura COMPLETA el movimiento del banco si coinciden el monto exacto y la fecha ±1 día.
- Varios candidatos → pending_review.
- Sin movimiento del banco: en efectivo crea un movimiento nuevo; con tarjeta, transferencia u
  otro medio queda un movimiento en pending_review, que la alerta del banco completa si llega después.
"""

import html
import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from email.message import EmailMessage

from app import categorize, service_db
from app.extract import bancolombia, invoice, llm
from app.extract.bancolombia import COLOMBIA, Alert
from app.ingest.mail import INVOICE_RULE

log = logging.getLogger("fsf.extract")


# ---------------------------------------------------------------- reglas puras (sin BD)
def local_date(when: datetime) -> date:
    return when.astimezone(COLOMBIA).date()


def matches(amount, when: datetime, txs: list[dict]) -> list[dict]:
    """Movimientos con el mismo monto exacto y fecha (en Colombia) a ±1 día."""
    day = local_date(when)
    return [
        t
        for t in txs
        if t["amount"] == amount and abs((local_date(t["occurred_at"]) - day).days) <= 1
    ]


def invoice_action(
    inv: invoice.Invoice, bank_txs: list[dict]
) -> tuple[str, dict | None]:
    """bank_txs: gastos del banco aún sin factura. → (complete, tx) | (review, None) | (new | new_pending, None)."""
    found = matches(inv.total, inv.issued_at, bank_txs)
    if len(found) == 1:
        return "complete", found[0]
    if found:
        return "review", None
    return ("new" if inv.payment_method == "cash" else "new_pending"), None


def alert_action(alert: Alert, invoice_txs: list[dict]) -> tuple[str, dict | None]:
    """invoice_txs: facturas pendientes que esperan su alerta. → (complete, tx) | (review, None) | (new, None)."""
    if alert.direction != "expense":
        return "new", None
    found = matches(alert.amount, alert.occurred_at, invoice_txs)
    if len(found) == 1:
        return "complete", found[0]
    return ("review" if found else "new"), None


# ---------------------------------------------------------------- correo
def body_text(msg: EmailMessage) -> str:
    part = msg.get_body(("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_subtype() == "html":
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text


def _zip_attachment(msg: EmailMessage) -> bytes | None:
    for part in msg.iter_attachments():
        if (part.get_filename() or "").lower().endswith(".zip"):
            return part.get_payload(decode=True)
    return None


# ---------------------------------------------------------------- BD (service_role, D4)
def _get(table: str, **params) -> list[dict]:
    return service_db.rest("GET", table, params=params).json()


def _txs(user_id: str, **filters) -> list[dict]:
    rows = _get(
        "transactions",
        user_id=f"eq.{user_id}",
        direction="eq.expense",
        select="id,amount::text,occurred_at,status,payment_method,source_ref",
        **filters,
    )
    for r in rows:  # amount::text: el numeric llega como texto exacto, nunca como float
        r["amount"] = Decimal(r["amount"])
        r["occurred_at"] = datetime.fromisoformat(r["occurred_at"])
    return rows


def accounts(user_id: str) -> list[dict]:
    """Cuentas del usuario (id, last4): una lectura por correo, compartida con el aviso."""
    return _get("accounts", user_id=f"eq.{user_id}", select="id,last4")


def _account_id(accounts: list[dict], last4: str | None) -> str | None:
    found = [a["id"] for a in accounts if last4 and a["last4"] == last4]
    return found[0] if len(found) == 1 else None


def _insert(row: dict) -> None:
    service_db.rest("POST", "transactions", json={"source": "email", **row})


def _update(tx_id: str, row: dict) -> None:
    service_db.rest("PATCH", "transactions", params={"id": f"eq.{tx_id}"}, json=row)


def _process_alert(
    user_id: str,
    email_id: str,
    msg: EmailMessage,
    received_at: datetime,
    user_accounts: list[dict],
) -> str:
    text = body_text(msg)
    alert = bancolombia.parse_alert(text)
    if alert.status == "no_movement":
        return "extracted"
    if (
        alert.reason == "sin_plantilla"
    ):  # solo lo que no encaja en ninguna plantilla va al LLM
        # La ventana de fechas se mide contra la llegada del correo, no contra ahora: así un
        # reproceso posterior no lo rechaza.
        alert = llm.extract(text, received_at)
    if alert.status not in ("confirmed", "pending_review") or alert.amount is None:
        log.info("alerta para revisión id=%s motivo=%s", email_id, alert.reason)
        return "pending_review"
    # Lo que viene del LLM nunca se confirma solo.
    status = "confirmed" if alert.status == "confirmed" else "pending_review"
    row = {
        "direction": alert.direction,
        "amount": str(alert.amount),
        "merchant": alert.merchant,
        "occurred_at": alert.occurred_at.isoformat(),
        "payment_method": alert.payment_method,
        "account_id": _account_id(user_accounts, alert.last4),
        "to_last4": alert.to_last4,
        "source_ref": f"bank:{email_id}",
        "status": status,
    }
    pending_invoices = _txs(
        user_id,
        amount=f"eq.{alert.amount}",
        status="eq.pending_review",
        source_ref="like.cufe:*",
        payment_method="neq.cash",
    )
    action, tx = alert_action(alert, pending_invoices)
    if action == "complete":
        # La factura llegó antes: su comercio (razón social) se conserva; el banco aporta lo demás.
        _update(tx["id"], {k: v for k, v in row.items() if k != "merchant"})
    else:
        _insert(
            {
                **row,
                **categorize.assign(
                    user_id, alert.merchant, alert.direction, alert.template
                ),
                "user_id": user_id,
                "status": "pending_review" if action == "review" else status,
            }
        )
    log.info(
        "alerta extraida id=%s plantilla=%s accion=%s", email_id, alert.template, action
    )
    return "extracted"


def _gmail_address(user_id: str) -> str | None:
    rows = _get("gmail_connections", user_id=f"eq.{user_id}", select="gmail_address")
    return rows[0]["gmail_address"] if rows else None


def _process_invoice(user_id: str, email_id: str, msg: EmailMessage) -> str:
    data, address = _zip_attachment(msg), _gmail_address(user_id)
    if data is None or address is None:
        log.info(
            "factura para revisión id=%s motivo=%s",
            email_id,
            "sin_zip" if data is None else "sin_gmail",
        )
        return "pending_review"
    check = invoice.check_invoice(data, address)
    if check.status != "confirmed":
        log.info("factura para revisión id=%s motivo=%s", email_id, check.reason)
        return "pending_review"
    inv = check.invoice
    if _get(
        "transactions",
        user_id=f"eq.{user_id}",
        invoice_cufe=f"eq.{inv.cufe}",
        select="id",
    ):
        log.info("factura repetida id=%s", email_id)
        return "extracted"
    bank_txs = _txs(
        user_id,
        amount=f"eq.{inv.total}",
        invoice_cufe="is.null",
        source_ref="like.bank:*",
        status="neq.dismissed",  # «No es un gasto mío»: no absorbe facturas
    )
    action, tx = invoice_action(inv, bank_txs)
    if action == "complete":
        _update(tx["id"], {"invoice_cufe": inv.cufe, "merchant": inv.supplier_name})
        # Cambió el comercio: se recategoriza, salvo que el usuario ya la corrigiera. La condición va
        # en la misma escritura por si corrige entre medias (null: movimiento de antes del Paso 10).
        service_db.rest(
            "PATCH",
            "transactions",
            params={
                "id": f"eq.{tx['id']}",
                "or": "(category_source.is.null,category_source.neq.usuario)",
            },
            json=categorize.assign(user_id, inv.supplier_name, "expense"),
        )
    elif action in ("new", "new_pending"):
        _insert(
            {
                "user_id": user_id,
                "direction": "expense",
                "amount": str(inv.total),
                "merchant": inv.supplier_name,
                "occurred_at": inv.issued_at.isoformat(),
                "payment_method": inv.payment_method,
                "invoice_cufe": inv.cufe,
                "source_ref": f"cufe:{inv.cufe}",
                "status": "confirmed" if action == "new" else "pending_review",
                # En efectivo: el dinero ya salió con el retiro en cajero, que es gasto (D12).
                "counts_in_budget": inv.payment_method != "cash",
                **categorize.assign(user_id, inv.supplier_name, "expense"),
            }
        )
    log.info("factura extraida id=%s accion=%s", email_id, action)
    return "pending_review" if action == "review" else "extracted"


def process(
    user_id: str,
    email_id: str,
    rule: str,
    msg: EmailMessage,
    received_at: datetime,
    user_accounts: list[dict] | None = None,
    before_mark: Callable[[], None] | None = None,
) -> str:
    """Extrae el movimiento de un correo recién guardado y marca su estado. Devuelve el estado.

    [user_accounts]: las cuentas ya leídas (si no, se leen). [before_mark] se llama con el movimiento
    ya escrito y antes de marcar el correo: el aviso no espera a esa escritura (RQN 04).

    Quien llama la serializa por usuario (ingest.store.user_lock): una alerta y su factura
    simultáneas deben verse entre sí.
    """
    if rule == INVOICE_RULE:
        status = _process_invoice(user_id, email_id, msg)
    elif rule == "bancolombia":
        if user_accounts is None:
            user_accounts = accounts(user_id)
        status = _process_alert(user_id, email_id, msg, received_at, user_accounts)
    else:
        status = "pending_review"
    if before_mark:
        before_mark()
    service_db.rest(
        "PATCH",
        "inbound_emails",
        params={"id": f"eq.{email_id}"},
        json={
            "status": status,
            **(
                {"extracted_at": datetime.now(UTC).isoformat()}
                if status == "extracted"
                else {}
            ),
        },
    )
    categorize.schedule(user_id)  # lo que quedó en 'pendiente' va al LLM, sin esperar
    return status
