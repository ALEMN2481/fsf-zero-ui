from dataclasses import dataclass
from time import monotonic
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Solo firmas asimétricas de Supabase; "none" y HS256 quedan rechazados.
ALGORITHMS = ["ES256", "RS256"]

JWKS_TTL = 600  # s: las claves en memoria caducan a los 10 min
KID_REFETCH_INTERVAL = 60  # s: como mucho una recarga por kid desconocido cada 60 s

_bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKSet | None = None
_loaded_at = 0.0
_last_kid_refetch = float("-inf")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    token: str  # se reenvía a Supabase para que aplique RLS (D4)
    # Nombre de la cuenta (Google: full_name o name en user_metadata), del JWT ya verificado.
    name: str | None = None


def _fetch_jwks() -> jwt.PyJWKSet:
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        r = httpx.get(url, timeout=5)
        r.raise_for_status()
        return jwt.PyJWKSet.from_dict(r.json())
    except (httpx.HTTPError, jwt.PyJWTError) as e:
        raise HTTPException(503, "No se pudo obtener el JWKS de Supabase") from e


def _load() -> None:
    global _jwks, _loaded_at
    _jwks, _loaded_at = _fetch_jwks(), monotonic()


def _signing_key(kid: str) -> jwt.PyJWK:
    global _last_kid_refetch
    if _jwks is None or monotonic() - _loaded_at > JWKS_TTL:
        _load()  # caducidad: una clave revocada deja de aceptarse en ≤ 10 min
    try:
        return _jwks[kid]
    except KeyError:
        # Posible rotación de claves; limitada para que kid inventados no saturen Supabase.
        if monotonic() - _last_kid_refetch < KID_REFETCH_INTERVAL:
            raise
        _last_kid_refetch = monotonic()
        _load()
        return _jwks[kid]


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if creds is None:
        raise HTTPException(401, "Falta el token")
    token = creds.credentials
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ALGORITHMS:
            raise HTTPException(401, "Algoritmo no permitido")
        key = _signing_key(header.get("kid", ""))
        claims = jwt.decode(
            token,
            key.key,
            algorithms=ALGORITHMS,
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except (jwt.PyJWTError, KeyError) as e:
        raise HTTPException(401, "Token inválido") from e
    return CurrentUser(id=claims["sub"], token=token, name=_name(claims))


def _name(claims: dict) -> str | None:
    meta = claims.get("user_metadata")
    if not isinstance(meta, dict):
        return None
    for key in ("full_name", "name"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:80]
    return None


User = Annotated[CurrentUser, Depends(current_user)]
