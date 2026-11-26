import base64
import json
import logging
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import categorize, gmail
from app.auth import CurrentUser, User
from app.config import settings
from app.engine import gps
from app.engine import store as engine_store
from app.extract import llm
from app.extract.bancolombia import COLOMBIA

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


def _call(
    user: CurrentUser,
    path: str,
    method: str = "GET",
    json: dict | None = None,
    prefer: str | None = None,
) -> httpx.Response:
    """API REST de Supabase con el JWT del usuario: RLS decide qué filas ve y escribe (D4)."""
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {user.token}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return httpx.request(
        method,
        f"{settings.supabase_url}/rest/v1/{path}",
        headers=headers,
        json=json,
        timeout=5,
    )


def _rest(user: CurrentUser, path: str, *args, **kwargs) -> list[dict]:
    r = _call(user, path, *args, **kwargs)
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


# ---------------------------------------------------------------- motor GPS (Paso 11, D12)
Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]


def _jsonable(value):
    """Decimal → texto (nunca float en el JSON); fechas → ISO."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _summary(user: CurrentUser) -> dict:
    today = _today()
    budget, movements, pocket_moves = engine_store.load(
        lambda path: _rest(user, path), today
    )
    return gps.summary(budget, today, movements, pocket_moves)


@app.get("/gps")
def gps_state(user: User) -> dict:
    """Saldo libre, presupuesto diario y semanal del periodo activo (fórmulas en D12).

    `reservado`: lo apartado en todos los bolsillos (no solo en el periodo), para la tarjeta
    «Reservado» de la principal (D14).
    """
    state = _summary(user)
    if state["estado"] == "ok":
        state["reservado"] = sum(_pocket_balances(user).values(), gps.ZERO)
    return _jsonable(state)


class BudgetIn(BaseModel):
    amount: Annotated[Money, Field(ge=0)]
    # Sin fechas (lo normal en la app): el mes en curso. Con fechas: un periodo a medida.
    period_start: date | None = None
    period_end: date | None = None


def _today() -> date:
    return datetime.now(COLOMBIA).date()  # los días se cuentan en hora de Colombia


@app.post("/budgets", status_code=201)
def save_budget(body: BudgetIn, user: User, response: Response) -> dict:
    """Crea el presupuesto (o cambia el monto del mes en curso). Se renueva solo cada mes."""
    fields = "select=id,period_start,period_end,amount::text"
    if (body.period_start is None) != (body.period_end is None):
        raise HTTPException(422, "Faltan las fechas del periodo")
    if body.period_start is None:
        today = _today()
        current = _rest(
            user, f"budgets?period_start=lte.{today}&period_end=gte.{today}&select=id"
        )
        if current:
            response.status_code = 200
            return _rest(
                user,
                f"budgets?id=eq.{current[0]['id']}&{fields}",
                "PATCH",
                {"amount": str(body.amount)},
                prefer="return=representation",
            )[0]
        renewed = engine_store.budget_for(lambda path: _rest(user, path), today)
        start, end = gps.month_bounds(today)
        if renewed is not None:  # empieza donde lo haría la renovación (sin solapar)
            start = renewed.start
    else:
        start, end = body.period_start, body.period_end
        if end < start:
            raise HTTPException(422, "El periodo termina antes de empezar")
    r = _call(
        user,
        f"budgets?{fields}",
        "POST",
        {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "amount": str(body.amount),
        },
        prefer="return=representation",
    )
    if r.status_code >= 300 and r.json().get("code") == "23P01":  # exclusión
        raise HTTPException(409, "El periodo se solapa con otro presupuesto")
    if r.status_code >= 300:
        raise HTTPException(502, "Error consultando Supabase")
    return r.json()[0]


@app.get("/budgets/suggestion")
def budget_suggestion(user: User) -> dict:
    """Referencia del mes anterior. Se propone lo que se gastó, no el 100 % de los ingresos."""
    ref = gps.reference(
        engine_store.previous_month(lambda path: _rest(user, path), _today())
    )
    return _jsonable(
        {
            "gasto_mes_anterior": ref["gasto"],
            "ingresos_mes_anterior": ref["ingresos"],
            "sugerido": ref["gasto"] if ref["gasto"] > 0 else None,
        }
    )


@app.get("/movements")
def recent_movements(
    user: User, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list:
    """Últimos movimientos (sin los descartados) con su tipo para el motor; sin cálculos."""
    rest = lambda path: _rest(user, path)
    own = engine_store.own_accounts(rest)
    rows = rest(
        f"transactions?status=neq.dismissed&order=occurred_at.desc&limit={limit}"
        "&select=id,amount::text,direction,status,merchant,occurred_at,counts_in_budget,"
        "to_last4,category:categories(id,name)"
    )
    return [
        {
            "id": r["id"],
            "monto": r["amount"],
            "direccion": r["direction"],
            "estado": r["status"],
            "comercio": r["merchant"],
            "fecha": r["occurred_at"],
            "categoria": (r["category"] or {}).get("name"),
            "categoria_id": (r["category"] or {}).get("id"),
            "tipo": engine_store.kind(r, own),
        }
        for r in rows
    ]


def _review(user: CurrentUser, tx_id: UUID, status: str) -> dict:
    """Solo un movimiento 'por confirmar' se confirma o se descarta."""
    done = _rest(
        user,
        f"transactions?id=eq.{tx_id}&status=eq.pending_review&select=id",
        "PATCH",
        {"status": status},
        prefer="return=representation",
    )
    if not done:
        if not _rest(user, f"transactions?id=eq.{tx_id}&select=id"):
            raise HTTPException(404, "Movimiento no encontrado")
        raise HTTPException(409, "El movimiento no está por confirmar")
    return {"id": str(tx_id), "estado": status}


@app.post("/transactions/{tx_id}/confirm")
def confirm_movement(tx_id: UUID, user: User) -> dict:
    return _review(user, tx_id, "confirmed")


@app.post("/transactions/{tx_id}/dismiss")
def dismiss_movement(tx_id: UUID, user: User) -> dict:
    """«No es un gasto mío»: queda descartado (no se borra) y el motor no lo cuenta."""
    return _review(user, tx_id, "dismissed")


def _pocket_balances(user: CurrentUser) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: gps.ZERO)
    for m in _rest(user, "pocket_movements?select=pocket_id,amount::text"):
        totals[m["pocket_id"]] += Decimal(m["amount"])
    return totals


@app.get("/pockets")
def pockets(user: User) -> dict:
    """Bolsillos con su saldo y su avance (% entero) y el total apartado: la app no calcula."""
    totals = _pocket_balances(user)
    rows = _rest(user, "pockets?select=id,name,target_amount::text&order=created_at")
    pockets = [
        {
            **p,
            "saldo": totals[p["id"]],
            "porcentaje": gps.progress(
                totals[p["id"]],
                Decimal(p["target_amount"]) if p["target_amount"] else None,
            ),
        }
        for p in rows
    ]
    return _jsonable(
        {"total": sum((p["saldo"] for p in pockets), gps.ZERO), "bolsillos": pockets}
    )


class PocketIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    target_amount: Annotated[Money, Field(gt=0)] | None = None


@app.post("/pockets", status_code=201)
def create_pocket(body: PocketIn, user: User) -> dict:
    row = {"name": body.name.strip()}
    if body.target_amount is not None:
        row["target_amount"] = str(body.target_amount)
    return _rest(
        user,
        "pockets?select=id,name,target_amount::text",
        "POST",
        row,
        prefer="return=representation",
    )[0]


class PocketMove(BaseModel):
    amount: Money  # + apartar, − retirar


@app.post("/pockets/{pocket_id}/movements", status_code=201)
def pocket_move(pocket_id: UUID, body: PocketMove, user: User) -> dict:
    """Apartar (amount > 0) o retirar (amount < 0). Si no se puede, 409 con el máximo que sí."""
    if body.amount == 0:
        raise HTTPException(422, "El monto no puede ser 0")
    if not _rest(user, f"pockets?id=eq.{pocket_id}&select=id"):
        raise HTTPException(404, "Bolsillo no encontrado")
    if body.amount > 0:
        # shortcut: comprobación sin bloqueo; dos apartados simultáneos podrían dejar el saldo libre
        # en negativo (se ve como negativo, nada se pierde). Si molesta, moverla a una función SQL.
        state = _summary(user)
        if state["estado"] != "ok":
            raise HTTPException(409, {"motivo": "sin_presupuesto", "maximo": "0.00"})
        if body.amount > state["maximo_apartable"]:
            raise HTTPException(
                409, {"motivo": "sobregiro", "maximo": str(state["maximo_apartable"])}
            )
    r = _call(
        user,
        "pocket_movements",
        "POST",
        {"pocket_id": str(pocket_id), "amount": str(body.amount)},
    )
    if r.status_code == 400 and r.json().get("code") == "23514":
        # El trigger de la BD: retirar más de lo apartado (también con retiros simultáneos).
        maximum = _pocket_balances(user)[str(pocket_id)]
        raise HTTPException(
            409, {"motivo": "saldo_insuficiente", "maximo": str(maximum)}
        )
    if r.status_code >= 300:
        raise HTTPException(502, "Error consultando Supabase")
    return {
        "pocket_id": str(pocket_id),
        "saldo": str(_pocket_balances(user)[str(pocket_id)]),
    }


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
