"""Integración contra Supabase LOCAL: dos usuarios a través de la API del backend."""

import uuid

import httpx
from fastapi.testclient import TestClient
from local_supabase import (
    ANON,
    PASSWORD,
    URL,
    admin,
    bearer,
    requires_local,
    sign_in,
    sign_up,
)

from app.main import app

pytestmark = requires_local


def test_a_does_not_read_b_through_api(users):
    a, b = users["a"], users["b"]
    # B crea una cuenta directamente en Supabase con su propio token
    r = httpx.post(
        f"{URL}/rest/v1/accounts",
        headers={
            "apikey": ANON,
            **bearer(b["token"]),
            "Prefer": "return=representation",
        },
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
    email = f"fsf-weak-{uuid.uuid4().hex[:8]}@test.local"
    r = sign_up(email, "corta12")  # 7 caracteres
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
