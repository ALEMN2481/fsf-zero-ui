"""Paso 14 (D16): avisos push. Unitarios sin BD e integración contra Supabase LOCAL con FCM simulado."""

import re
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import test_daily_api
import test_extract_store
from fastapi.testclient import TestClient
from local_supabase import bearer, requires_local
from test_extract_store import alert_email, svc

from app import gmail, push
from app.coach import cop
from app.config import settings
from app.extract.bancolombia import COLOMBIA
from app.ingest.store import ingest
from app.main import app

client = TestClient(app)
env = test_extract_store.env  # usuario A con Gmail y cuenta *1111
tx = test_daily_api.tx
MERCHANT = "SUPERMERCADO EJEMPLO SAS"


# ---------------------------------------------------------------- textos (sin BD)
def test_spent_message_has_engine_figures_and_no_merchant():
    state = {
        "estado": "ok",
        "disponible_hoy": Decimal(158333),
        "exceso": Decimal(0),
    }
    m = push.spent_message(Decimal(45900), state)
    assert m == {
        "title": "Nuevo gasto registrado",
        "body": "Registramos $ 45.900. Hoy puedes gastar $ 158.333.",
        "public_title": "Nuevo gasto registrado",
    }
    over = {
        "estado": "ok",
        "disponible_hoy": Decimal(-5000),
        "exceso": Decimal(5000),
    }
    assert push.spent_message(Decimal(45900), over)["body"].endswith(
        "Hoy vas $ 5.000 por encima de tu cuota."
    )
    assert push.spent_message(Decimal(45900), {"estado": "sin_presupuesto"})[
        "body"
    ] == ("Registramos $ 45.900.")


def test_review_and_reconnect_messages_have_no_figures():
    for m in (push.REVIEW_MESSAGE, push.RECONNECT_MESSAGE):
        assert not re.search(r"\d|\$", " ".join(m.values()))
        assert m["public_title"] == m["title"]


def test_disabled_without_credentials():
    assert not push.enabled()  # conftest: sin FCM en los tests
    assert push.send("u", push.SPENT, push.REVIEW_MESSAGE) == 0


# ---------------------------------------------------------------- integración
class FakeFcm:
    def __init__(self, status=200):
        self.status, self.sent = status, []

    def __call__(self, token, data):
        self.sent.append((token, data))
        return httpx.Response(
            self.status, text="" if self.status == 200 else "UNREGISTERED"
        )


@pytest.fixture
def fcm(monkeypatch):
    fake = FakeFcm()
    monkeypatch.setattr(settings, "fcm_credentials_file", "simulado.json")
    monkeypatch.setattr(settings, "fcm_project_id", "proyecto-simulado")
    monkeypatch.setattr(push, "_post", fake)
    return fake


def device(token, user, name="tel"):
    r = client.post("/devices", headers=bearer(user["token"]), json={"token": token})
    assert r.status_code == 204, r.text


def today_alert(amount="45.900,00"):
    now = datetime.now(COLOMBIA)
    return alert_email(
        "",
        f"Bancolombia: Compraste ${amount} en {MERCHANT} con tu T.Cred *1111, el "
        f"{now:%d/%m/%Y} a las {now:%H:%M}. Si tienes dudas, encuentranos aqui: 000 000 0000.",
    )


@requires_local
def test_new_expense_sends_one_notice_with_engine_figures(env, users, fcm):
    user_id, _ = env
    a = users["a"]
    assert (
        client.post(
            "/budgets", headers=bearer(a["token"]), json={"amount": "3000000"}
        ).status_code
        == 201
    )
    device("tok-a", a)
    assert (
        ingest(user_id, today_alert(), "gmail", "gmail:1", received_ms=1234) == "stored"
    )

    assert len(fcm.sent) == 1
    token, data = fcm.sent[0]
    gps = client.get("/gps", headers=bearer(a["token"])).json()
    assert token == "tok-a" and data["tipo"] == push.SPENT
    assert data["body"] == (
        f"Registramos {cop(Decimal(45900))}. Hoy puedes gastar {cop(Decimal(gps['disponible_hoy']))}."
    )
    assert (
        data["public_title"] == "Nuevo gasto registrado"
        and data["received_ms"] == "1234"
    )
    assert not any("SUPERMERCADO" in v for v in data.values())  # sin comercio
    moved = client.get(
        f"/transactions/{data['transaction_id']}", headers=bearer(a["token"])
    ).json()
    assert moved["monto"] == "45900.00"
    # Nada más que avisar: un aviso por movimiento.
    assert push.new_movements(user_id) == 0 and len(fcm.sent) == 1


@requires_local
def test_review_income_and_own_transfer(env, users, fcm):
    user_id, _ = env
    device("tok-a", users["a"])
    tx(user_id, "10000", status="pending_review")
    tx(user_id, "500000", direction="income")  # sin avisos de ingresos
    tx(user_id, "20000", to_last4="1111")  # a su propia cuenta *1111: no es gasto
    assert push.new_movements(user_id) == 1
    assert fcm.sent[0][1]["tipo"] == push.REVIEW
    assert not re.search(r"\d", fcm.sent[0][1]["body"])


@requires_local
def test_dead_tokens_are_removed(env, users, fcm):
    user_id, _ = env
    device("tok-viejo", users["a"])
    fcm.status = 404
    tx(user_id, "10000")
    assert push.new_movements(user_id) == 0
    assert svc("GET", "device_tokens?token=eq.tok-viejo&select=token") == []


@requires_local
def test_devices_move_between_accounts_and_are_private(users, monkeypatch):
    a, b = users["a"], users["b"]
    device("tel-compartido", a)
    device("tel-compartido", b)  # en ese teléfono entró otra cuenta: el token pasa a B
    assert svc("GET", "device_tokens?token=eq.tel-compartido&select=user_id") == [
        {"user_id": b["id"]}
    ]
    # A no puede quitarle el token a B.
    r = client.request(
        "DELETE",
        "/devices",
        headers=bearer(a["token"]),
        json={"token": "tel-compartido"},
    )
    assert r.status_code == 204
    assert svc("GET", "device_tokens?token=eq.tel-compartido&select=user_id") == [
        {"user_id": b["id"]}
    ]
    r = client.request(
        "DELETE",
        "/devices",
        headers=bearer(b["token"]),
        json={"token": "tel-compartido"},
    )
    assert svc("GET", "device_tokens?token=eq.tel-compartido&select=token") == []


@requires_local
def test_movement_of_another_user_is_404(env, users):
    user_id, _ = env
    row = tx(user_id, "10000")
    assert (
        client.get(
            f"/transactions/{row['id']}", headers=bearer(users["b"]["token"])
        ).status_code
        == 404
    )


@requires_local
def test_gmail_reconnect_notice_only_on_the_change(env, users, fcm, monkeypatch):
    user_id, _ = env
    device("tok-a", users["a"])

    def expired(data):
        raise gmail.NeedsReconnect()

    monkeypatch.setattr(gmail, "_token_request", expired)
    monkeypatch.setattr(gmail.crypto, "decrypt", lambda *a: b"refresh")
    conn = {"user_id": user_id, "key_version": 1, "refresh_token_encrypted": "\\x00"}
    assert gmail._access_token(conn) is None
    assert gmail._access_token(conn) is None  # ya estaba caída: no se repite el aviso
    assert [d["tipo"] for _, d in fcm.sent] == [push.RECONNECT]
    status = svc("GET", f"gmail_connections?user_id=eq.{user_id}&select=status")
    assert status == [{"status": "needs_reconnect"}]
