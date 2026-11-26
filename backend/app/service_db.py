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
    if r.is_error:
        # Sin la URL: sus filtros pueden llevar datos personales (un correo, un comercio) y el
        # mensaje de la excepción acaba en los logs con el traceback (Paso 15).
        raise httpx.HTTPStatusError(
            f"Supabase {method} {table.split('?')[0]} respondió {r.status_code}",
            request=r.request,
            response=r,
        )
    return r


def to_bytea(blob: bytes) -> str:
    return "\\x" + blob.hex()


def from_bytea(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("\\x"))
