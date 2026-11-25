"""Conexión con Gmail, avisos de Pub/Sub y lectura de correos (sin red: Google y la BD simulados)."""

import base64
import hashlib
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import gmail, service_db
from app.auth import CurrentUser, current_user
from app.config import settings
from app.ingest import crypto
from app.main import _HideQueryString, app

SAMPLE = (Path(__file__).parent / "samples" / "bancolombia_compra.eml").read_bytes()
PUSH_URL = "https://tunel.example/gmail/push"
PUSH_SA = "fsf-pubsub-push@proyecto.iam.gserviceaccount.com"
GOOGLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
BANK = "Alertas <alertasynotificaciones@notificacionesbancolombia.com>"


class FakeDB:
    """Tabla gmail_connections en memoria con el subconjunto de PostgREST que usa gmail.py."""

    def __init__(self):
        self.conns: dict[str, dict] = {}

    def _match(self, row, params):
        for key, cond in (params or {}).items():
            if key in ("select", "on_conflict"):
                continue
            op, _, value = cond.partition(".")
            if op == "eq" and str(row.get(key)) != value:
                return False
            if op == "lt" and not str(row.get(key) or "") < value:
                return False
        return True

    def rest(self, method, table, *, params=None, json=None, prefer=None):
        assert table == "gmail_connections"
        rows = []
        if method == "GET":
            rows = [dict(r) for r in self.conns.values() if self._match(r, params)]
        elif method == "POST":
            self.conns[json["user_id"]] = {
                **self.conns.get(json["user_id"], {}),
                **json,
            }
        elif method == "PATCH":
            for r in self.conns.values():
                if self._match(r, params):
                    r.update(json)
        elif method == "DELETE":
            self.conns = {
                k: r for k, r in self.conns.items() if not self._match(r, params)
            }
        return SimpleNamespace(json=lambda: rows)

    def add(
        self,
        user_id="user-a",
        address="usuario.ejemplo@gmail.com",
        refresh="ref-viejo",
        **extra,
    ):
        version, blob = crypto.encrypt(refresh.encode(), user_id.encode())
        self.conns[user_id] = {
            "user_id": user_id,
            "gmail_address": address,
            "status": "active",
            "key_version": version,
            "refresh_token_encrypted": service_db.to_bytea(blob),
            "history_id": 100,
            "watch_expires_at": "2026-12-01T00:00:00+00:00",
            **extra,
        }


class FakeGoogle:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_error: str | None = None
        self.scope = gmail.SCOPE
        self.history = (200, {"historyId": "130", "history": []})
        # id -> (De, Asunto, correo crudo[, etiquetas]); sin etiquetas = bandeja de entrada
        self.messages: dict[str, tuple] = {}
        self.fail: dict[
            str, tuple[int, dict]
        ] = {}  # fragmento de URL -> (estado, cuerpo)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        url, path = str(req.url), req.url.path
        for fragment, (status, body) in self.fail.items():
            if fragment in url:
                return httpx.Response(status, json=body)
        if url == gmail.TOKEN_URL:
            if self.token_error:
                return httpx.Response(400, json={"error": self.token_error})
            return httpx.Response(
                200,
                json={
                    "access_token": "acc-1",
                    "refresh_token": "ref-nuevo",
                    "scope": f"openid {self.scope}",
                },
            )
        if url.startswith(gmail.REVOKE_URL):
            return httpx.Response(200)
        if path.endswith("/profile"):
            return httpx.Response(
                200,
                json={"emailAddress": "Usuario.Ejemplo@gmail.com", "historyId": "100"},
            )
        if path.endswith("/watch"):
            return httpx.Response(
                200,
                json={
                    "historyId": "120",
                    "expiration": str(int(time.time() * 1000) + 7 * 86400000),
                },
            )
        if path.endswith("/history"):
            status, body = self.history
            return httpx.Response(status, json=body)
        mid = path.rsplit("/", 1)[-1]
        sender, subject, raw, *rest = self.messages[mid]
        labels = rest[0] if rest else ["INBOX"]
        if req.url.params["format"] == "metadata":
            headers = [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
            ]
            return httpx.Response(
                200,
                json={
                    "id": mid,
                    "internalDate": str(int(time.time() * 1000) - 2000),
                    "labelIds": labels,
                    "payload": {"headers": headers},
                },
            )
        return httpx.Response(
            200,
            json={"id": mid, "raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
        )

    def calls(self, fragment: str) -> int:
        return sum(fragment in str(r.url) for r in self.requests)


@pytest.fixture
def env(monkeypatch):
    for name, value in {
        "email_keys": f"1:{base64.b64encode(os.urandom(32)).decode()}",
        "google_oauth_client_id": "cliente-ejemplo.apps.googleusercontent.com",
        "google_oauth_client_secret": "secreto-cliente-ejemplo",
        "gmail_pubsub_topic": "projects/proyecto/topics/gmail-fsf",
        "pubsub_push_audience": PUSH_URL,
        "pubsub_push_service_account": PUSH_SA,
    }.items():
        monkeypatch.setattr(settings, name, value)
    db, google, ingested = FakeDB(), FakeGoogle(), []
    monkeypatch.setattr(service_db, "rest", db.rest)
    monkeypatch.setattr(
        gmail, "http", httpx.Client(transport=httpx.MockTransport(google))
    )
    monkeypatch.setattr(
        gmail,
        "ingest",
        lambda user, raw, source, dedupe_key: (
            ingested.append((user, dedupe_key)) or "stored"
        ),
    )
    monkeypatch.setattr(
        gmail, "_google_signing_key", lambda token: GOOGLE_KEY.public_key()
    )
    monkeypatch.setattr(gmail, "_states", {})
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id="user-a", token="jwt-usuario"
    )
    yield SimpleNamespace(
        db=db, google=google, ingested=ingested, client=TestClient(app)
    )
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- conectar
def start(env) -> dict[str, str]:
    r = env.client.post("/gmail/connect")
    assert r.status_code == 200
    return {k: v[0] for k, v in parse_qs(urlparse(r.json()["url"]).query).items()}


def test_connect_url_asks_only_gmail_readonly_offline_with_pkce(env):
    q = start(env)
    assert q["scope"] == gmail.SCOPE  # permiso incremental: solo este permiso nuevo
    assert (q["access_type"], q["prompt"], q["include_granted_scopes"]) == (
        "offline",
        "consent",
        "true",
    )
    assert q["redirect_uri"] == settings.gmail_redirect_uri
    user, verifier = gmail.take_state(q["state"])
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert (user, q["code_challenge"], q["code_challenge_method"]) == (
        "user-a",
        expected,
        "S256",
    )


def test_callback_exchanges_code_in_backend_and_stores_encrypted_token(env):
    q = start(env)
    r = env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "codigo-1"},
        follow_redirects=False,
    )
    assert r.headers["location"] == f"{settings.gmail_return_url}?status=ok"
    form = parse_qs(env.google.requests[0].content.decode())
    assert form["code"] == ["codigo-1"] and form["client_secret"] == [
        "secreto-cliente-ejemplo"
    ]
    assert "code_verifier" in form
    conn = env.db.conns["user-a"]
    assert (conn["gmail_address"], conn["status"], conn["history_id"]) == (
        "usuario.ejemplo@gmail.com",
        "active",
        120,
    )
    blob = service_db.from_bytea(conn["refresh_token_encrypted"])
    assert b"ref-nuevo" not in blob
    assert crypto.decrypt(conn["key_version"], blob, b"user-a") == b"ref-nuevo"
    # el state no se puede reutilizar
    again = env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "x"},
        follow_redirects=False,
    )
    assert again.headers["location"].endswith("status=error")


def test_callback_without_gmail_permission_saves_nothing(env):
    env.google.scope = "openid"
    q = start(env)
    r = env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "c"},
        follow_redirects=False,
    )
    assert r.headers["location"].endswith("status=error") and env.db.conns == {}


def test_expired_state_is_refused(env, monkeypatch):
    q = start(env)
    monkeypatch.setattr(
        gmail, "monotonic", lambda: time.monotonic() + gmail.STATE_TTL + 1
    )
    assert gmail.take_state(q["state"]) is None


# ---------------------------------------------------------------- avisos de Pub/Sub
def push_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": PUSH_URL,
        "email": PUSH_SA,
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
        **overrides,
    }
    return jwt.encode(claims, GOOGLE_KEY, algorithm="RS256", headers={"kid": "k"})


def push(env, token: str | None, address="usuario.ejemplo@gmail.com", history_id=125):
    data = base64.b64encode(
        f'{{"emailAddress":"{address}","historyId":{history_id}}}'.encode()
    ).decode()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return env.client.post(
        "/gmail/push", json={"message": {"data": data}}, headers=headers
    )


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(None, id="sin-token"),
        pytest.param(
            {"aud": "https://otro.example/gmail/push"}, id="audiencia-incorrecta"
        ),
        pytest.param(
            {"email": "otra@proyecto.iam.gserviceaccount.com"}, id="otra-cuenta"
        ),
        pytest.param({"email_verified": False}, id="correo-no-verificado"),
        pytest.param({"iss": "https://falso.example"}, id="emisor-incorrecto"),
        pytest.param({"exp": int(time.time()) - 10}, id="caducado"),
    ],
)
def test_push_without_valid_google_oidc_is_rejected(env, token, caplog):
    env.db.add()
    raw = push_token(**token) if token is not None else None
    r = push(env, raw)
    assert r.status_code == 401
    assert "aviso rechazado motivo=" in caplog.text  # la causa queda en el log...
    assert raw is None or raw not in caplog.text  # ...pero nunca el token
    assert env.google.requests == []  # no se toca Gmail


def test_push_downloads_only_candidates_and_dedupes_by_gmail_id(env, caplog):
    caplog.set_level(logging.INFO)
    env.db.add()
    env.google.history = (
        200,
        {
            "historyId": "130",
            "history": [
                {
                    "messagesAdded": [
                        {"message": {"id": "m-banco"}},
                        {"message": {"id": "m-boletin"}},
                    ]
                },
                {
                    "messagesAdded": [{"message": {"id": "m-banco"}}]
                },  # repetido en otra entrada
            ],
        },
    )
    env.google.messages = {
        "m-banco": (BANK, "Alertas y Notificaciones", SAMPLE),
        "m-boletin": (
            "Ofertas <ofertas@tienda-ejemplo.example>",
            "50% de descuento",
            b"no se descarga",
        ),
    }
    assert push(env, push_token()).status_code == 204
    assert env.ingested == [("user-a", "gmail:m-banco")]
    assert env.google.calls("format=raw") == 1  # el boletín no se descarga entero
    assert env.db.conns["user-a"]["history_id"] == 130
    assert "latencia gmail→guardado ms=" in caplog.text  # medida para RQN 04


def test_invalid_grant_marks_needs_reconnect_without_retrying(env):
    env.db.add()
    env.google.token_error = "invalid_grant"
    assert (
        push(env, push_token()).status_code == 204
    )  # se confirma: reintentar no lo arregla
    assert env.db.conns["user-a"]["status"] == "needs_reconnect"
    tokens_before = env.google.calls(gmail.TOKEN_URL)
    assert push(env, push_token()).status_code == 204
    assert env.google.calls(gmail.TOKEN_URL) == tokens_before  # ya no se intenta más
    assert env.ingested == []


def test_old_history_id_skips_to_current(env):
    env.db.add()
    env.google.history = (404, {"error": {"code": 404}})
    assert push(env, push_token(), history_id=140).status_code == 204
    assert env.db.conns["user-a"]["history_id"] == 140 and env.ingested == []


def test_push_for_unknown_mailbox_is_acknowledged(env):
    assert push(env, push_token(), address="desconocido@gmail.com").status_code == 204
    assert env.google.requests == []


# ---------------------------------------------------------------- mantenimiento
def test_renew_watches_only_renews_expiring_ones(env):
    env.db.add("user-a", "a@gmail.com", watch_expires_at="2000-01-01T00:00:00+00:00")
    env.db.add("user-b", "b@gmail.com", watch_expires_at="2999-01-01T00:00:00+00:00")
    assert gmail.renew_watches() == 1
    assert env.db.conns["user-a"]["watch_expires_at"] > "2026"
    assert env.google.calls("/watch") == 1


def test_disconnect_revokes_and_deletes(env):
    env.db.add(refresh="ref-a-revocar")
    assert env.client.post("/gmail/disconnect").status_code == 204
    revoke = [r for r in env.google.requests if str(r.url).startswith(gmail.REVOKE_URL)]
    assert parse_qs(revoke[0].content.decode())["token"] == ["ref-a-revocar"]
    assert env.db.conns == {}


# ---------------------------------------------------------------- logs
def test_access_log_hides_query_string():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/gmail/callback?state=s&code=codigo-secreto", "1.1", 303), None,
    )  # fmt: skip
    _HideQueryString().filter(record)
    assert (
        "codigo-secreto" not in record.getMessage()
        and "/gmail/callback" in record.getMessage()
    )


def test_gmail_flow_logs_no_tokens_or_addresses(env, caplog):
    caplog.set_level(logging.DEBUG)
    q = start(env)
    env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "codigo-1"},
        follow_redirects=False,
    )
    env.google.history = (
        200,
        {
            "historyId": "130",
            "history": [{"messagesAdded": [{"message": {"id": "m-banco"}}]}],
        },
    )
    env.google.messages = {"m-banco": (BANK, "Alertas y Notificaciones", SAMPLE)}
    push(env, push_token())
    for secret in (
        "codigo-1",
        "ref-nuevo",
        "acc-1",
        "secreto-cliente-ejemplo",
        "usuario.ejemplo@gmail",
        q["state"],
    ):
        assert secret.lower() not in caplog.text.lower(), secret


def test_failed_callback_logs_only_the_error_type(env, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)

    def boom(user_id, code, verifier):
        raise RuntimeError(f"fallo con code={code} y refresh_token=ref-filtrado")

    monkeypatch.setattr(gmail, "connect", boom)
    q = start(env)
    r = env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "codigo-secreto-9"},
        follow_redirects=False,
    )
    assert r.headers["location"].endswith("status=error")
    assert "RuntimeError" in caplog.text
    assert "codigo-secreto-9" not in caplog.text and "ref-filtrado" not in caplog.text


@pytest.mark.parametrize(
    "fragment, status, body, expected",
    [
        pytest.param(
            gmail.TOKEN_URL,
            401,
            {"error": "invalid_client", "error_description": "detalle-privado"},
            "paso=token http=401 motivo=invalid_client",
            id="canje",
        ),
        pytest.param(
            "/watch",
            403,
            {
                "error": {
                    "code": 403,
                    "message": "detalle-privado projects/x/topics/y",
                    "status": "PERMISSION_DENIED",
                    "errors": [{"reason": "forbidden", "message": "detalle-privado"}],
                }
            },
            "paso=watch http=403 motivo=PERMISSION_DENIED/forbidden",
            id="watch",
        ),
    ],
)
def test_failed_callback_logs_step_status_and_reason_only(
    env, caplog, fragment, status, body, expected
):
    caplog.set_level(logging.DEBUG)
    env.google.fail = {fragment: (status, body)}
    q = start(env)
    r = env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "codigo-secreto-8"},
        follow_redirects=False,
    )
    assert r.headers["location"].endswith("status=error")
    assert expected in caplog.text
    assert (
        "detalle-privado" not in caplog.text and "codigo-secreto-8" not in caplog.text
    )


# ---------------------------------------------------------------- carpetas (D8)
INVOICE_SUBJECT = "900000000;COMERCIO EJEMPLO SAS;FE-1;01;COMERCIO EJEMPLO"
INVOICE_FROM = "Comercio <facturas@comercio-ejemplo.example>"


@pytest.mark.parametrize(
    "sender, subject, labels, downloaded",
    [
        pytest.param(
            BANK, "Alertas", ["SPAM", "UNREAD"], True, id="banco-en-spam-se-guarda"
        ),
        pytest.param(BANK, "Alertas", ["INBOX"], True, id="banco-en-entrada-se-guarda"),
        pytest.param(
            INVOICE_FROM,
            INVOICE_SUBJECT,
            ["SPAM"],
            False,
            id="factura-en-spam-se-descarta",
        ),
        pytest.param(
            INVOICE_FROM,
            INVOICE_SUBJECT,
            ["INBOX"],
            True,
            id="factura-en-entrada-se-guarda",
        ),
        pytest.param(
            BANK, "Alertas", ["SENT", "INBOX"], False, id="enviados-se-descarta"
        ),
        pytest.param(BANK, "Alertas", ["DRAFT"], False, id="borradores-se-descarta"),
        pytest.param(BANK, "Alertas", ["TRASH"], False, id="papelera-se-descarta"),
        pytest.param(
            BANK, "Alertas", ["CATEGORY_UPDATES"], False, id="archivado-se-descarta"
        ),
    ],
)
def test_folder_rules(env, sender, subject, labels, downloaded):
    env.db.add()
    env.google.history = (
        200,
        {
            "historyId": "130",
            "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
        },
    )
    env.google.messages = {"m1": (sender, subject, SAMPLE, labels)}
    assert push(env, push_token()).status_code == 204
    assert env.google.calls("format=raw") == int(
        downloaded
    )  # si no se acepta, ni se descarga
    assert env.ingested == ([("user-a", "gmail:m1")] if downloaded else [])


def test_watch_and_history_cover_the_whole_mailbox(env):
    q = start(env)
    env.client.get(
        "/gmail/callback",
        params={"state": q["state"], "code": "c"},
        follow_redirects=False,
    )
    watch = next(r for r in env.google.requests if r.url.path.endswith("/watch"))
    assert "labelIds" not in watch.content.decode()
    env.db.add()
    push(env, push_token())
    history = next(r for r in env.google.requests if r.url.path.endswith("/history"))
    assert "labelId" not in history.url.params
