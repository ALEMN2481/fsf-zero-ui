"""Acceso a Supabase con service_role: solo para procesos sin usuario, como la ingesta (D4)."""

import httpx

from app.config import settings


def rest(
    method: str, table: str, *, params=None, json=None, prefer: str | None = None
) -> httpx.Response:
    key = settings.supabase_service_role_key
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    r = httpx.request(
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
