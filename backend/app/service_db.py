"""Acceso a Supabase con service_role: solo para procesos sin usuario, como la ingesta (D4)."""

import httpx

from app.config import settings


def new_client() -> httpx.Client:
    """Un cliente para todo el proceso (Supabase y FCM). Crear uno por llamada armaba su contexto TLS
    cada vez: ~360 ms por consulta en Windows (Paso 14). Lo cierra el lifespan al apagar."""
    return httpx.Client(timeout=httpx.Timeout(10, connect=5))


http = new_client()


def rest(
    method: str, table: str, *, params=None, json=None, prefer: str | None = None
) -> httpx.Response:
    key = settings.supabase_service_role_key
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    r = http.request(
        method,
        f"{settings.supabase_url}/rest/v1/{table}",
        params=params,
        json=json,
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()  # el mensaje de error lleva la URL, nunca la clave
    return r


def to_bytea(blob: bytes) -> str:
    return "\\x" + blob.hex()


def from_bytea(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("\\x"))
