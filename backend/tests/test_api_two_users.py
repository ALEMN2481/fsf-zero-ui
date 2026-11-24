"""Integración contra Supabase LOCAL: dos usuarios a través de la API del backend.

Requiere SUPABASE_URL, SUPABASE_ANON_KEY y SUPABASE_SERVICE_ROLE_KEY del stack local
(`supabase status -o env`). Nunca corre contra la nube: crear usuarios allí requiere
confirmación del supervisor.
"""

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import settings
from app.main import app

URL = os.getenv("SUPABASE_URL", "")
ANON = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
PASSWORD = "clave-de-prueba-1"

LOCAL_READY = bool(ANON and SERVICE and ("127.0.0.1" in URL or "localhost" in URL))
# En la tarea db de la CI se exige el stack local: saltarse sería un falso verde.
if os.getenv("REQUIRE_SUPABASE") and not LOCAL_READY:
    raise RuntimeError("REQUIRE_SUPABASE=1 pero no hay Supabase local configurado")

pytestmark = pytest.mark.skipif(not LOCAL_READY, reason="requiere Supabase local (supabase start)")


def admin(method, path, **kw):
    h = {"apikey": SERVICE, "Authorization": f"Bearer {SERVICE}"}
    return httpx.request(method, f"{URL}/auth/v1/admin/{path}", headers=h, timeout=10, **kw)


def sign_in(email, password=PASSWORD):
    return httpx.post(
        f"{URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON},
        json={"email": email, "password": password},
        timeout=10,
    )


def sign_up(email, password):
    return httpx.post(
        f"{URL}/auth/v1/signup", headers={"apikey": ANON}, json={"email": email, "password": password}, timeout=10
    )


@pytest.fixture
def users(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", URL)
    monkeypatch.setattr(settings, "supabase_anon_key", ANON)
    monkeypatch.setattr(auth, "_jwks", None)
    created = {}
    for name in ("a", "b"):
        email = f"fsf-{name}-{uuid.uuid4().hex[:8]}@test.local"
        r = admin("POST", "users", json={"email": email, "password": PASSWORD, "email_confirm": True})
        assert r.status_code == 200, r.text
        token = sign_in(email).json()["access_token"]
        created[name] = {"id": r.json()["id"], "email": email, "token": token}
    yield created
    for u in created.values():
        admin("DELETE", f"users/{u['id']}")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_does_not_read_b_through_api(users):
    a, b = users["a"], users["b"]
    # B crea una cuenta directamente en Supabase con su propio token
    r = httpx.post(
        f"{URL}/rest/v1/accounts",
        headers={"apikey": ANON, **bearer(b["token"]), "Prefer": "return=representation"},
        json={"name": "Cuenta privada de B", "kind": "debit"},
        timeout=10,
    )
    assert r.status_code == 201, r.text

    client = TestClient(app)
    assert client.get("/accounts").status_code == 401  # sin token

    seen_by_b = client.get("/accounts", headers=bearer(b["token"]))
    assert seen_by_b.status_code == 200
    assert [x["name"] for x in seen_by_b.json()] == ["Cuenta privada de B"]

    seen_by_a = client.get("/accounts", headers=bearer(a["token"]))
    assert seen_by_a.status_code == 200
    assert seen_by_a.json() == []  # el backend no filtra: lo bloquea RLS

    me_a = client.get("/me", headers=bearer(a["token"]))
    assert me_a.status_code == 200 and me_a.json()["id"] == a["id"]


def test_password_shorter_than_8_is_rejected():
    r = sign_up(f"fsf-weak-{uuid.uuid4().hex[:8]}@test.local", "corta12")  # 7 caracteres
    assert r.status_code == 422
    assert r.json().get("error_code") == "weak_password"


def test_unconfirmed_email_cannot_sign_in():
    email = f"fsf-unconfirmed-{uuid.uuid4().hex[:8]}@test.local"
    signup = sign_up(email, PASSWORD)
    assert signup.status_code == 200, signup.text
    try:
        r = sign_in(email)
        assert r.status_code == 400
        assert r.json().get("error_code") == "email_not_confirmed"
    finally:
        admin("DELETE", f"users/{signup.json()['id']}")
