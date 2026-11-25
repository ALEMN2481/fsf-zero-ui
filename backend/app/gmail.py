"""Conexión con Gmail (D7): OAuth con permiso incremental, avisos de Pub/Sub y lectura de correos nuevos.

Los logs nunca llevan tokens, códigos, direcciones de Gmail ni contenido de correos.
"""

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from app import service_db
from app.config import settings
from app.ingest import crypto, mail
from app.ingest.store import ingest

log = logging.getLogger("fsf.gmail")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
STATE_TTL = 600  # s
WATCH_RENEW_BEFORE = timedelta(days=2)

http = httpx.Client(timeout=10)  # los tests lo cambian por uno con MockTransport


class NeedsReconnect(Exception):
    """Google rechazó el refresh_token (invalid_grant): el usuario debe volver a conectar Gmail."""


# ---------------------------------------------------------------- OAuth
# shortcut: state en memoria; con varias instancias del backend o tras un reinicio se pierde.
# Para producción (Paso 16), guardarlo en la BD con caducidad.
_states: dict[str, tuple[str, str, float]] = {}


def authorization_url(user_id: str) -> str:
    now = monotonic()
    for key in [k for k, (_, _, exp) in _states.items() if exp < now]:
        del _states[key]
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    _states[state] = (user_id, verifier, now + STATE_TTL)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.gmail_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "include_granted_scopes": "true",  # permiso incremental: se suma a los del inicio de sesión
        "access_type": "offline",  # para recibir refresh_token
        "prompt": "consent",  # Google solo entrega refresh_token si se muestra el consentimiento
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def take_state(state: str) -> tuple[str, str] | None:
    """Un solo uso: devuelve (user_id, verifier) si el state existe y no caducó."""
    entry = _states.pop(state, None)
    if entry is None or entry[2] < monotonic():
        return None
    return entry[0], entry[1]


def _token_request(data: dict) -> dict:
    data = {
        **data,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
    }
    r = http.post(TOKEN_URL, data=data)
    if r.status_code == 400 and r.json().get("error") == "invalid_grant":
        raise NeedsReconnect
    r.raise_for_status()
    return r.json()


def _gmail(method: str, access_token: str, path: str, **kw) -> httpx.Response:
    return http.request(
        method,
        f"{GMAIL_URL}/{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        **kw,
    )


def _watch(access_token: str) -> dict:
    r = _gmail(
        "POST",
        access_token,
        "watch",
        json={
            "topicName": settings.gmail_pubsub_topic,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        },
    )
    r.raise_for_status()
    return r.json()  # {"historyId": "...", "expiration": "<epoch ms>"}


def _expiry(watch: dict) -> str:
    return datetime.fromtimestamp(int(watch["expiration"]) / 1000, UTC).isoformat()


def connect(user_id: str, code: str, verifier: str) -> None:
    """Intercambia el código en el backend, guarda el refresh_token cifrado y activa los avisos."""
    tokens = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.gmail_redirect_uri,
            "code_verifier": verifier,
        }
    )
    if SCOPE not in tokens.get("scope", "").split():
        raise PermissionError("El usuario no concedió gmail.readonly")
    if not tokens.get("refresh_token"):
        raise PermissionError("Google no entregó refresh_token")
    access = tokens["access_token"]
    profile = _gmail("GET", access, "profile")
    profile.raise_for_status()
    watch = _watch(access)
    version, blob = crypto.encrypt(tokens["refresh_token"].encode(), user_id.encode())
    service_db.rest(
        "POST",
        "gmail_connections",
        params={"on_conflict": "user_id"},
        prefer="resolution=merge-duplicates",
        json={
            "user_id": user_id,
            "gmail_address": profile.json()["emailAddress"].lower(),
            "status": "active",
            "key_version": version,
            "refresh_token_encrypted": service_db.to_bytea(blob),
            "history_id": int(watch["historyId"]),
            "watch_expires_at": _expiry(watch),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    log.info("gmail conectado user=%s", user_id)


def _update(user_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now(UTC).isoformat()
    service_db.rest(
        "PATCH", "gmail_connections", params={"user_id": f"eq.{user_id}"}, json=fields
    )


def _access_token(conn: dict) -> str | None:
    """Access token nuevo; ante invalid_grant marca la conexión como caída y no reintenta."""
    refresh = crypto.decrypt(
        conn["key_version"],
        service_db.from_bytea(conn["refresh_token_encrypted"]),
        conn["user_id"].encode(),
    ).decode()
    try:
        return _token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh}
        )["access_token"]
    except NeedsReconnect:
        _update(conn["user_id"], status="needs_reconnect")
        log.warning("gmail necesita reconexión user=%s", conn["user_id"])
        return None


_CONN_FIELDS = "user_id,status,key_version,refresh_token_encrypted,history_id"


# ---------------------------------------------------------------- avisos de Pub/Sub
def _google_signing_key(token: str):
    return _google_jwks.get_signing_key_from_jwt(token).key


_google_jwks = jwt.PyJWKClient(GOOGLE_CERTS, cache_keys=True)


def verify_push(authorization: str | None) -> None:
    """El aviso debe traer un token OIDC de Google emitido para nuestra cuenta de servicio y endpoint."""
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or not settings.pubsub_push_audience
    ):
        raise HTTPException(401, "Aviso sin autenticar")
    token = authorization.removeprefix("Bearer ")
    try:
        claims = jwt.decode(
            token,
            _google_signing_key(token),
            algorithms=["RS256"],
            audience=settings.pubsub_push_audience,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["exp", "iat", "aud", "iss", "email"]},
        )
    except (jwt.PyJWTError, KeyError) as e:
        raise HTTPException(401, "Aviso con token inválido") from e
    if (
        claims.get("email") != settings.pubsub_push_service_account
        or claims.get("email_verified") is not True
    ):
        raise HTTPException(401, "Aviso de otra cuenta de servicio")


def process_notification(gmail_address: str, history_id: int) -> int:
    """Lee los correos nuevos del buzón desde el último history_id. Devuelve cuántos guardó."""
    rows = service_db.rest(
        "GET",
        "gmail_connections",
        params={"gmail_address": f"eq.{gmail_address.lower()}", "select": _CONN_FIELDS},
    ).json()
    if not rows or rows[0]["status"] != "active":
        return 0  # buzón desconocido o caído: se confirma el aviso sin reintentar
    conn = rows[0]
    access = _access_token(conn)
    if access is None:
        return 0

    message_ids: list[str] = []
    latest, page = history_id, None
    while True:
        params = {
            "startHistoryId": conn["history_id"],
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
        }
        if page:
            params["pageToken"] = page
        r = _gmail("GET", access, "history", params=params)
        if r.status_code == 404:
            # shortcut: history_id demasiado viejo (> ~1 semana sin avisos); se salta al actual sin
            # recuperar lo perdido. Mejorar con una búsqueda por remitentes si llega a pasar.
            log.warning("gmail history_id caducado user=%s", conn["user_id"])
            break
        r.raise_for_status()
        body = r.json()
        latest = max(latest, int(body.get("historyId", 0)))
        for h in body.get("history", []):
            message_ids += [m["message"]["id"] for m in h.get("messagesAdded", [])]
        page = body.get("nextPageToken")
        if not page:
            break

    stored = 0
    for mid in dict.fromkeys(message_ids):  # sin repetidos, en orden
        meta = _gmail(
            "GET",
            access,
            f"messages/{mid}",
            params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
        )
        if meta.status_code == 404:
            continue  # borrado antes de leerlo
        meta.raise_for_status()
        headers = {
            h["name"].lower(): h["value"]
            for h in meta.json().get("payload", {}).get("headers", [])
        }
        if not mail.is_candidate(headers.get("from", ""), headers.get("subject", "")):
            continue  # no se descarga el correo completo
        full = _gmail("GET", access, f"messages/{mid}", params={"format": "raw"})
        full.raise_for_status()
        raw = base64.urlsafe_b64decode(full.json()["raw"] + "==")
        if ingest(conn["user_id"], raw, "gmail", dedupe_key=f"gmail:{mid}") == "stored":
            stored += 1

    _update(conn["user_id"], history_id=latest)
    log.info(
        "aviso gmail procesado user=%s mensajes=%d guardados=%d",
        conn["user_id"],
        len(message_ids),
        stored,
    )
    return stored


# ---------------------------------------------------------------- mantenimiento
def renew_watches() -> int:
    """Renueva los avisos que caducan pronto (Gmail los corta a los 7 días). Pensado para ejecutarse a diario."""
    limit = (datetime.now(UTC) + WATCH_RENEW_BEFORE).isoformat()
    rows = service_db.rest(
        "GET",
        "gmail_connections",
        params={
            "status": "eq.active",
            "watch_expires_at": f"lt.{limit}",
            "select": _CONN_FIELDS,
        },
    ).json()
    renewed = 0
    for conn in rows:
        access = _access_token(conn)
        if access is None:
            continue
        _update(conn["user_id"], watch_expires_at=_expiry(_watch(access)))
        renewed += 1
    return renewed


def disconnect(user_id: str) -> None:
    """Revoca el permiso en Google (si se puede) y borra la conexión."""
    rows = service_db.rest(
        "GET",
        "gmail_connections",
        params={"user_id": f"eq.{user_id}", "select": _CONN_FIELDS},
    ).json()
    if rows:
        conn = rows[0]
        refresh = crypto.decrypt(
            conn["key_version"],
            service_db.from_bytea(conn["refresh_token_encrypted"]),
            user_id.encode(),
        ).decode()
        try:
            http.post(REVOKE_URL, data={"token": refresh})
        except httpx.HTTPError:
            log.warning("no se pudo revocar el token en Google user=%s", user_id)
    service_db.rest("DELETE", "gmail_connections", params={"user_id": f"eq.{user_id}"})
