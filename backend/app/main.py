import base64
import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app import categorize, gmail
from app.auth import CurrentUser, User
from app.config import settings
from app.extract import llm

# Los mensajes de la app (fsf.*) solo llevan metadatos; sin esto uvicorn solo mostraría avisos y errores.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Precarga el LLM de respaldo en segundo plano: el arranque no espera ni falla si Ollama no está.
    threading.Thread(target=llm.preload, daemon=True).start()
    yield


app = FastAPI(title="Finanzas Sin Filtro API", lifespan=lifespan)
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
# httpcore en DEBUG registra las cabeceras de respuesta, que repiten la URL con los filtros (p. ej. el
# monto al buscar el movimiento del banco que completa una factura).
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _rest(
    user: CurrentUser,
    path: str,
    method: str = "GET",
    json: dict | None = None,
    prefer: str | None = None,
) -> list[dict]:
    """API REST de Supabase con el JWT del usuario: RLS decide qué filas ve y escribe (D4)."""
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {user.token}",
    }
    if prefer:
        headers["Prefer"] = prefer
    r = httpx.request(
        method,
        f"{settings.supabase_url}/rest/v1/{path}",
        headers=headers,
        json=json,
        timeout=5,
    )
    if r.status_code >= 300:
        raise HTTPException(502, "Error consultando Supabase")
    return r.json() if r.content else []


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


# ---------------------------------------------------------------- categorías (Paso 10, D11)
@app.get("/categories")
def categories(user: User) -> list[dict]:
    """Globales (user_id null) y propias del usuario."""
    return _rest(user, "categories?select=id,name,user_id&order=name")


class CategoryChange(BaseModel):
    category_id: UUID


@app.patch("/transactions/{tx_id}/category")
def set_category(tx_id: UUID, body: CategoryChange, user: User) -> dict:
    """Corrige la categoría y aprende la regla comercio → categoría para los siguientes movimientos."""
    tx = _rest(user, f"transactions?id=eq.{tx_id}&select=merchant")
    if not tx:
        raise HTTPException(404, "Movimiento no encontrado")
    if not _rest(user, f"categories?id=eq.{body.category_id}&select=id"):
        raise HTTPException(422, "Categoría no disponible")
    change = {"category_id": str(body.category_id), "category_source": "usuario"}
    _rest(user, f"transactions?id=eq.{tx_id}", "PATCH", change)
    key = categorize.merchant_key(tx[0]["merchant"] or "")
    if key:
        _rest(
            user,
            "category_rules?on_conflict=user_id,merchant_key",
            "POST",
            {"merchant_key": key, "category_id": change["category_id"]},
            prefer="resolution=merge-duplicates",
        )
    return {"id": str(tx_id), **change}


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
        except Exception as e:  # noqa: BLE001 - cualquier fallo vuelve a la app como error
            # Solo el tipo: el mensaje o la traza de una excepción podrían llevar el código o un token.
            detail = (
                gmail.google_error_summary(e)
                if isinstance(e, httpx.HTTPStatusError)
                else ""
            )
            log.error(
                "falló la conexión con gmail user=%s error=%s %s",
                pending[0],
                type(e).__name__,
                detail,
            )
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
