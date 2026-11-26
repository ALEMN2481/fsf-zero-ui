"""Avisos push con FCM HTTP v1 (Paso 14, D16).

- Mensajes **solo de datos**: la app (servicio nativo de Android) arma la notificación con
  VISIBILITY_PRIVATE y una versión pública genérica para la pantalla de bloqueo.
- Gasto registrado: monto del movimiento y «hoy puedes gastar» del motor (nunca del LLM), sin
  comercio. Por confirmar y reconexión de Gmail: sin cifras. Sin avisos de ingresos.
- Un aviso por movimiento: se reclama con notified_at en la misma escritura.
- Los logs llevan tipo, usuario y resultado; nunca el token ni el contenido.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import quote

import httpx
import jwt

from app import service_db
from app.coach import cop
from app.config import settings
from app.engine import gps
from app.engine import store as engine_store
from app.extract.bancolombia import COLOMBIA

log = logging.getLogger("fsf.push")

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SPENT, REVIEW, RECONNECT = "gasto_registrado", "por_confirmar", "reconectar_gmail"
CATEGORY = "categorizar"

# ---------------------------------------------------------------- textos (sin comercio)


def spent_message(amount: Decimal, state: dict) -> dict:
    """Gasto registrado: monto del movimiento y lo que queda hoy, del motor."""
    body = f"Registramos {cop(amount)}."
    if state.get("estado") == "ok":
        if state["disponible_hoy"] >= 0:
            body += f" Hoy puedes gastar {cop(state['disponible_hoy'])}."
        else:
            body += f" Hoy vas {cop(state['exceso'])} por encima de tu cuota."
    return {
        "title": "Nuevo gasto registrado",
        "body": body,
        "public_title": "Nuevo gasto registrado",
    }


def cash_invoice_message(amount: Decimal) -> dict:
    """Factura en efectivo: no baja lo de hoy (ya se contó con el retiro en cajero, D12)."""
    return {
        "title": "Nuevo gasto registrado",
        "body": f"Registramos tu factura de {cop(amount)} en efectivo. Ya estaba contada en tu retiro.",
        "public_title": "Nuevo gasto registrado",
    }


CATEGORY_MESSAGE = {
    "title": "¿En qué categoría va este gasto?",
    "body": "No pudimos saberlo. Toca para elegirla.",
    "public_title": "¿En qué categoría va este gasto?",
}
REVIEW_MESSAGE = {
    "title": "Detectamos un gasto",
    "body": "Necesitamos que lo confirmes. Toca para revisarlo.",
    "public_title": "Detectamos un gasto",
}
RECONNECT_MESSAGE = {
    "title": "Tu conexión con Gmail se detuvo",
    "body": "Toca para reconectarla y seguir registrando tus gastos.",
    "public_title": "Tu conexión con Gmail se detuvo",
}

# ---------------------------------------------------------------- envío (FCM HTTP v1)

_token_lock = threading.Lock()
_token: tuple[str, float] | None = None  # (access token, caduca en epoch)
_project: str | None = None


def enabled() -> bool:
    return bool(settings.fcm_credentials_file)


def _project_id() -> str:
    """El proyecto de FCM es el de la cuenta de servicio (campo project_id de su clave, D16)."""
    global _project
    if _project is None:
        with open(settings.fcm_credentials_file, encoding="utf-8") as f:
            _project = json.load(f)["project_id"]
    return _project


def _access_token() -> str:
    """Token OAuth de la cuenta de servicio (JWT firmado con su clave). Se reutiliza ~55 min."""
    global _token
    with _token_lock:
        if _token and _token[1] > time.time() + 60:
            return _token[0]
        with open(settings.fcm_credentials_file, encoding="utf-8") as f:
            info = json.load(f)
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": info["client_email"],
                "scope": SCOPE,
                "aud": info["token_uri"],
                "iat": now,
                "exp": now + 3600,
            },
            info["private_key"],
            algorithm="RS256",
        )
        r = service_db.http.post(
            info["token_uri"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        _token = (body["access_token"], now + int(body.get("expires_in", 3600)))
        return _token[0]


def _post(token: str, data: dict[str, str]) -> httpx.Response:
    return service_db.http.post(
        f"https://fcm.googleapis.com/v1/projects/{_project_id()}/messages:send",
        headers={"Authorization": f"Bearer {_access_token()}"},
        json={
            "message": {"token": token, "data": data, "android": {"priority": "high"}}
        },
        timeout=10,
    )


Sender = Callable[[str, dict[str, str]], httpx.Response]


def _unregistered(r: httpx.Response) -> bool:
    """Token muerto solo si FCM lo dice en su error JSON. Un 404 en HTML (p. ej. un FCM_PROJECT_ID
    mal puesto) no lo es: borrarlo dejaría al teléfono sin avisos."""
    try:
        details = r.json().get("error", {}).get("details", [])
    except ValueError:
        return False
    return any(d.get("errorCode") == "UNREGISTERED" for d in details)


def _device_tokens(user_id: str) -> list[str]:
    return [
        r["token"]
        for r in service_db.rest(
            "GET",
            "device_tokens",
            params={"user_id": f"eq.{user_id}", "select": "token"},
        ).json()
    ]


def send(
    user_id: str,
    kind: str,
    message: dict,
    extra: dict | None = None,
    post: Sender | None = None,
    tokens: list[str] | None = None,
) -> int:
    """Envía [message] a todos los dispositivos del usuario. Devuelve cuántos lo aceptaron.

    [tokens]: los del usuario, si ya se leyeron. Los que FCM da por muertos (UNREGISTERED) se
    borran. Nunca lanza: un aviso que falla no debe romper la ingesta.
    """
    if post is None and not enabled():
        return 0
    post = post or _post
    data = {"tipo": kind, **message, **{k: str(v) for k, v in (extra or {}).items()}}
    if tokens is None:
        try:
            tokens = _device_tokens(user_id)
        except httpx.HTTPError as e:
            log.error(
                "aviso no enviado tipo=%s user=%s error=%s",
                kind,
                user_id,
                type(e).__name__,
            )
            return 0
    sent = 0
    for token in tokens:
        try:
            r = post(token, data)
        except (httpx.HTTPError, OSError, ValueError, KeyError) as e:
            log.error(
                "aviso no enviado tipo=%s user=%s error=%s",
                kind,
                user_id,
                type(e).__name__,
            )
            continue
        if r.status_code == 200:
            sent += 1
        elif _unregistered(r):
            service_db.rest("DELETE", "device_tokens", params={"token": f"eq.{token}"})
            log.info("token borrado motivo=no_registrado user=%s", user_id)
        else:
            log.warning(
                "aviso rechazado tipo=%s user=%s http=%d", kind, user_id, r.status_code
            )
    log.info(
        "aviso tipo=%s user=%s dispositivos=%d enviados=%d",
        kind,
        user_id,
        len(tokens),
        sent,
    )
    return sent


# ---------------------------------------------------------------- disparadores


def user_rest(user_id: str) -> engine_store.Rest:
    """Lecturas del motor con service_role, siempre filtradas por el usuario (sin RLS aquí)."""

    def rest(path: str) -> list[dict]:
        table, _, query = path.partition("?")
        r = service_db.rest("GET", f"{table}?{query}&user_id=eq.{quote(user_id)}")
        return r.json()

    return rest


def _today() -> date:
    return datetime.now(COLOMBIA).date()


def new_movements(
    user_id: str,
    received_ms: int | None = None,
    post: Sender | None = None,
    accounts: list[dict] | None = None,
) -> int:
    """Tras la ingesta: un aviso por cada gasto nuevo (confirmado o por confirmar) sin avisar.

    [accounts]: las cuentas del usuario ya leídas en la ingesta (id, last4); si no, se leen.
    El reclamo (notified_at) va antes del envío: si FCM falla, ese aviso se pierde pero nunca sale
    dos veces; el movimiento ya está en la app.
    """
    if post is None and not enabled():
        return 0
    rows = service_db.rest(
        "GET",
        "transactions",
        params={
            "user_id": f"eq.{user_id}",
            "notified_at": "is.null",
            "direction": "eq.expense",  # sin avisos de ingresos ni devoluciones
            "status": "in.(confirmed,pending_review)",
            "select": "id,amount::text,status,to_last4,counts_in_budget",
            "order": "created_at",
        },
    ).json()
    if not rows:
        return 0
    rest = user_rest(user_id)
    if accounts is None:
        own = engine_store.own_accounts(rest)
    else:
        own = {a["last4"] for a in accounts if a["last4"]}
    # Tokens y datos del motor no dependen entre sí: en paralelo (RQN 04). El estado del motor ya
    # incluye todos los movimientos nuevos, así que vale para cada aviso de esta tanda.
    with ThreadPoolExecutor(2) as pool:
        tokens = pool.submit(_device_tokens, user_id)
        state = None
        if any(r["status"] == "confirmed" and r["counts_in_budget"] for r in rows):
            state = pool.submit(lambda: gps.summary(*_load(rest, _today(), own)))
        tokens, state = tokens.result(), state and state.result()
    count = 0
    for row in rows:
        claimed = service_db.rest(
            "PATCH",
            "transactions",
            params={"id": f"eq.{row['id']}", "notified_at": "is.null", "select": "id"},
            json={"notified_at": datetime.now(UTC).isoformat()},
            prefer="return=representation",
        ).json()
        if not claimed or (row["to_last4"] and row["to_last4"] in own):
            continue  # ya avisado, o transferencia entre cuentas propias (no es gasto)
        extra = {"transaction_id": row["id"]}
        if received_ms:
            extra["received_ms"] = (
                received_ms  # RQN 04: el teléfono mide correo → aviso
            )
        if row["status"] == "pending_review":
            message, kind = REVIEW_MESSAGE, REVIEW
        elif not row["counts_in_budget"]:  # factura en efectivo
            message, kind = cash_invoice_message(Decimal(row["amount"])), SPENT
        else:
            message, kind = spent_message(Decimal(row["amount"]), state), SPENT
        count += send(user_id, kind, message, extra, post, tokens)
    return count


def _load(rest, today, own=None):
    budget, movements, pockets = engine_store.load(rest, today, own)
    return budget, today, movements, pockets


def ask_category(user_id: str, tx_id: str, post: Sender | None = None) -> int:
    """Ni las reglas ni el LLM supieron la categoría: se le pregunta al usuario (sin cifras).

    Usa el mismo enlace que el aviso del gasto, así que en el teléfono lo reemplaza."""
    return send(user_id, CATEGORY, CATEGORY_MESSAGE, {"transaction_id": tx_id}, post)


def gmail_disconnected(user_id: str, post: Sender | None = None) -> int:
    return send(user_id, RECONNECT, RECONNECT_MESSAGE, None, post)
