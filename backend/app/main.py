import base64
import json
import logging
from typing import Annotated

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Response
from fastapi.responses import RedirectResponse

from app import gmail
from app.auth import CurrentUser, User
from app.config import settings

app = FastAPI(title="Finanzas Sin Filtro API")
log = logging.getLogger("fsf.api")


class _HideQueryString(logging.Filter):
    """El log de accesos de uvicorn no registra la query: en /gmail/callback lleva el código de Google."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            args[2] = str(args[2]).split("?", 1)[0]
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(_HideQueryString())
# httpx registra en INFO la URL de cada petición saliente, y sus filtros pueden llevar datos (p. ej. la
# dirección de Gmail al buscar la conexión). Solo avisos y errores.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _rest(user: CurrentUser, path: str) -> list[dict]:
    """GET a la API REST de Supabase con el JWT del usuario: RLS decide qué filas ve (D4)."""
    r = httpx.get(
        f"{settings.supabase_url}/rest/v1/{path}",
        headers={
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {user.token}",
        },
        timeout=5,
    )
    if r.status_code != 200:
        raise HTTPException(502, "Error consultando Supabase")
    return r.json()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/me")
def me(user: User) -> dict:
    rows = _rest(user, "profiles?select=id,display_name,created_at")
    if not rows:
        raise HTTPException(404, "Perfil no encontrado")
    # Estado de Gmail: null (sin conectar), 'active' o 'needs_reconnect' (el aviso al usuario es del Paso 14).
    conn = _rest(user, "gmail_connections?select=status")
    return {**rows[0], "gmail_status": conn[0]["status"] if conn else None}


@app.get("/accounts")
def accounts(user: User) -> list[dict]:
    # Sin filtro por user_id a propósito: el aislamiento lo garantiza RLS.
    return _rest(user, "accounts?select=id,name,kind,last4,created_at&order=created_at")


# ---------------------------------------------------------------- Gmail (Paso 08B, D7)
@app.post("/gmail/connect")
def gmail_connect(user: User) -> dict[str, str]:
    if not (settings.google_oauth_client_id and settings.gmail_pubsub_topic):
        raise HTTPException(503, "Gmail no está configurado en el backend")
    return {"url": gmail.authorization_url(user.id)}


@app.get("/gmail/callback")
def gmail_callback(
    state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    """Google vuelve aquí tras el consentimiento; el backend canjea el código y devuelve al usuario a la app."""
    pending = gmail.take_state(state)
    result = "error"
    if pending and code and not error:
        try:
            gmail.connect(pending[0], code, pending[1])
            result = "ok"
        except Exception:
            log.exception("falló la conexión con gmail user=%s", pending[0])
    # 'status' y no 'error'/'code': supabase_flutter trataría esos parámetros como un inicio de sesión.
    return RedirectResponse(
        f"{settings.gmail_return_url}?status={result}", status_code=303
    )


@app.post("/gmail/push", status_code=204)
def gmail_push(
    body: Annotated[dict, Body()], authorization: Annotated[str | None, Header()] = None
) -> Response:
    """Aviso de Pub/Sub: un buzón conectado tiene novedades."""
    gmail.verify_push(authorization)
    try:
        data = json.loads(base64.b64decode(body["message"]["data"]))
        address, history_id = data["emailAddress"], int(data["historyId"])
    except (KeyError, ValueError, TypeError):
        return Response(
            status_code=204
        )  # mensaje malformado: se confirma para que no se reintente
    gmail.process_notification(
        address, history_id
    )  # un fallo pasajero da 500 y Pub/Sub reintenta
    return Response(status_code=204)


@app.post("/gmail/disconnect", status_code=204)
def gmail_disconnect(user: User) -> Response:
    gmail.disconnect(user.id)
    return Response(status_code=204)
