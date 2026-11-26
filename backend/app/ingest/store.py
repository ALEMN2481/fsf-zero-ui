"""Recibe un correo crudo de un usuario y, si pasa el filtro, lo guarda cifrado (Paso 08).

Los logs solo llevan metadatos: nunca asunto, cuerpo, direcciones completas ni claves.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

from app import push, service_db
from app.extract import pipeline
from app.ingest import crypto, mail

log = logging.getLogger("fsf.ingest")

# Una extracción a la vez por usuario: una alerta y su factura que llegan juntas deben verse entre
# sí (si no, se cuentan dos veces).
# shortcut: candados en memoria, válidos con un solo proceso (la expo, D17); con varias instancias,
# un bloqueo en la BD (pg_advisory_xact_lock por usuario).
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def user_lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def _aad(user_id: str, digest: str) -> bytes:
    return f"{user_id}:{digest}".encode()


def ingest(
    user_id: str,
    raw: bytes,
    source: str = "gmail",
    dedupe_key: str | None = None,
    received_ms: int | None = None,
) -> str:
    """Devuelve 'stored', 'duplicate', 'too_large' o el motivo del descarte ('no_rule', 'discarded', 'dkim').

    [dedupe_key] identifica el mensaje para no guardarlo dos veces (en Gmail, su id de mensaje);
    sin él se usa el Message-ID, que pone el remitente.
    """
    try:
        msg = mail.parse(raw)
    except ValueError:
        log.info("correo descartado motivo=too_large")
        return "too_large"

    decision = mail.classify(msg)
    if not decision.accepted:
        log.info(
            "correo descartado motivo=%s regla=%s dominio=%s",
            decision.reason,
            decision.rule,
            decision.sender_domain,
        )
        return decision.reason

    clean = mail.sanitize(msg, decision.rule)
    if len(clean) > mail.MAX_STORED_BYTES:
        log.info("correo descartado motivo=too_large regla=%s", decision.rule)
        return "too_large"

    digest = mail.message_hash(msg, raw, dedupe_key)
    version, blob = crypto.encrypt(clean, _aad(user_id, digest))
    r = service_db.rest(
        "POST",
        "inbound_emails",
        params={"on_conflict": "user_id,message_hash", "select": "id,received_at"},
        prefer="resolution=ignore-duplicates,return=representation",
        json={
            "user_id": user_id,
            "source": source,
            "rule": decision.rule,
            "sender_domain": decision.sender_domain,
            "message_hash": digest,
            "key_version": version,
            "raw_encrypted": service_db.to_bytea(blob),
        },
    )
    rows = r.json()
    if not rows:
        log.info("correo duplicado regla=%s", decision.rule)
        return "duplicate"
    log.info(
        "correo guardado id=%s regla=%s dominio=%s",
        rows[0]["id"],
        decision.rule,
        decision.sender_domain,
    )
    user_accounts: list[dict] | None = None
    notified = False

    def notify() -> None:
        """El aviso sale en cuanto el movimiento está escrito, antes de marcar el correo (RQN 04)."""
        nonlocal notified
        notified = True
        try:
            # [received_ms]: cuándo lo recibió Gmail (RQN 04)
            push.new_movements(user_id, received_ms, accounts=user_accounts)
        except Exception as e:  # noqa: BLE001 - un aviso que falla no debe perder el correo
            log.error("falló el aviso id=%s error=%s", rows[0]["id"], type(e).__name__)

    with user_lock(user_id):
        try:
            user_accounts = pipeline.accounts(user_id)  # una sola lectura por correo
            pipeline.process(
                user_id,
                rows[0]["id"],
                decision.rule,
                msg,
                datetime.fromisoformat(rows[0]["received_at"]),
                user_accounts,
                before_mark=notify,
            )
        except Exception as e:  # noqa: BLE001 - el correo ya está guardado; un fallo no debe perderlo
            # Queda en pending_extraction (se reprocesa). Solo el tipo: el mensaje podría llevar datos.
            log.error(
                "falló la extracción id=%s error=%s", rows[0]["id"], type(e).__name__
            )
        if not notified:
            notify()  # la extracción falló antes: igual se avisa lo que haya quedado sin avisar
    return "stored"


def reprocess_pending(min_age_s: int = 60, user_ids: list[str] | None = None) -> int:
    """Vuelve a extraer los correos que quedaron en pending_extraction (p. ej. por un fallo o un
    reinicio). Devuelve cuántos extrajo. [min_age_s]: no toca los que se están procesando ahora.

    Idempotente: si el movimiento de una alerta ya existe (se insertó y falló al marcar el correo),
    solo se marca el correo. Las facturas ya se protegen por su CUFE.
    """
    limit = (datetime.now(UTC) - timedelta(seconds=min_age_s)).isoformat()
    params = {
        "status": "eq.pending_extraction",
        "received_at": f"lt.{limit}",
        "select": "id,user_id,rule,message_hash,key_version,raw_encrypted,received_at",
        "order": "received_at",
    }
    if user_ids is not None:
        params["user_id"] = f"in.({','.join(user_ids)})"
    done, touched = 0, set()
    for row in service_db.rest("GET", "inbound_emails", params=params).json():
        user_id, email_id = row["user_id"], row["id"]
        try:
            with user_lock(user_id):
                existing = service_db.rest(
                    "GET",
                    "transactions",
                    params={
                        "user_id": f"eq.{user_id}",
                        "source_ref": f"eq.bank:{email_id}",
                        "select": "id",
                    },
                ).json()
                if existing:
                    service_db.rest(
                        "PATCH",
                        "inbound_emails",
                        params={"id": f"eq.{email_id}"},
                        json={
                            "status": "extracted",
                            "extracted_at": datetime.now(UTC).isoformat(),
                        },
                    )
                else:
                    raw = crypto.decrypt(
                        row["key_version"],
                        service_db.from_bytea(row["raw_encrypted"]),
                        _aad(user_id, row["message_hash"]),
                    )
                    pipeline.process(
                        user_id,
                        email_id,
                        row["rule"],
                        mail.parse(raw),
                        datetime.fromisoformat(row["received_at"]),
                    )
            done += 1
            touched.add(user_id)
        except Exception as e:  # noqa: BLE001 - uno que falla no frena a los demás
            log.error("falló el reproceso id=%s error=%s", email_id, type(e).__name__)
    for user_id in touched:
        try:
            push.new_movements(user_id)
        except Exception as e:  # noqa: BLE001
            log.error("falló el aviso del reproceso error=%s", type(e).__name__)
    log.info("reproceso de correos pendientes extraidos=%d", done)
    return done
