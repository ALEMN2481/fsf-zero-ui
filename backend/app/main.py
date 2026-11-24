import httpx
from fastapi import FastAPI, HTTPException

from app.auth import CurrentUser, User
from app.config import settings

app = FastAPI(title="Finanzas Sin Filtro API")


def _rest(user: CurrentUser, path: str) -> list[dict]:
    """GET a la API REST de Supabase con el JWT del usuario: RLS decide qué filas ve (D4)."""
    r = httpx.get(
        f"{settings.supabase_url}/rest/v1/{path}",
        headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {user.token}"},
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
    return rows[0]


@app.get("/accounts")
def accounts(user: User) -> list[dict]:
    # Sin filtro por user_id a propósito: el aislamiento lo garantiza RLS.
    return _rest(user, "accounts?select=id,name,kind,last4,created_at&order=created_at")
