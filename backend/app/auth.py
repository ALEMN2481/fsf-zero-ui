from dataclasses import dataclass
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Solo firmas asimétricas de Supabase; "none" y HS256 quedan rechazados.
ALGORITHMS = ["ES256", "RS256"]

_bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKSet | None = None


@dataclass(frozen=True)
class CurrentUser:
    id: str
    token: str  # se reenvía a Supabase para que aplique RLS (D4)


def _fetch_jwks() -> jwt.PyJWKSet:
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        r = httpx.get(url, timeout=5)
        r.raise_for_status()
        return jwt.PyJWKSet.from_dict(r.json())
    except (httpx.HTTPError, jwt.PyJWTError) as e:
        raise HTTPException(503, "No se pudo obtener el JWKS de Supabase") from e


def _signing_key(kid: str) -> jwt.PyJWK:
    global _jwks
    if _jwks is None:
        _jwks = _fetch_jwks()
    try:
        return _jwks[kid]
    except KeyError:
        _jwks = _fetch_jwks()  # posible rotación de claves: una sola recarga
        return _jwks[kid]


def current_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> CurrentUser:
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
    return CurrentUser(id=claims["sub"], token=token)


User = Annotated[CurrentUser, Depends(current_user)]
