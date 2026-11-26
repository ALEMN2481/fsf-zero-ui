"""Paso 14 (D16): avisos push. Unitarios sin BD e integración contra Supabase LOCAL con FCM simulado."""

import logging
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

from app import categorize, gmail, push
from app.coach import cop
from app.config import settings
from app.extract import llm
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


def test_cash_invoice_message_does_not_offer_what_is_left_today():
    m = push.cash_invoice_message(Decimal(15800))
    assert m["body"] == (
        f"Registramos tu factura de {cop(Decimal(15800))} en efectivo. Ya estaba contada en tu retiro."
    )
    assert "puedes gastar" not in m["body"] and m["public_title"] == m["title"]


def test_review_and_reconnect_messages_have_no_figures():
    for m in (push.REVIEW_MESSAGE, push.RECONNECT_MESSAGE, push.CATEGORY_MESSAGE):
        assert not re.search(r"\d|\$", " ".join(m.values()))
        assert m["public_title"] == m["title"]


def test_disabled_without_credentials():
    assert not push.enabled()  # conftest: sin FCM en los tests
    assert push.send("u", push.SPENT, push.REVIEW_MESSAGE) == 0


# ---------------------------------------------------------------- integración
class FakeFcm:
    def __init__(self, status=200):
        self.status, self.sent, self.html = status, [], False

    def __call__(self, token, data):
        self.sent.append((token, data))
        if self.status == 200:
            return httpx.Response(200, json={"name": "projects/p/messages/1"})
        if (
            self.status == 404 and not self.html
        ):  # así responde FCM HTTP v1 a un token muerto
            return httpx.Response(
                404,
                json={
                    "error": {
                        "status": "NOT_FOUND",
                        "details": [{"errorCode": "UNREGISTERED"}],
                    }
                },
            )
        return httpx.Response(self.status, text="<html>Not Found</html>")


@pytest.fixture
def fcm(monkeypatch):
    fake = FakeFcm()
    monkeypatch.setattr(settings, "fcm_credentials_file", "simulado.json")
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


def _email_and_movements(user_id):
    emails = svc("GET", f"inbound_emails?user_id=eq.{user_id}&select=status")
    txs = svc("GET", f"transactions?user_id=eq.{user_id}&select=notified_at")
    return [e["status"] for e in emails], [t["notified_at"] is not None for t in txs]


@requires_local
def test_if_fcm_fails_the_email_is_consistent_and_a_retry_does_not_notify_twice(
    env, users, fcm
):
    user_id, _ = env
    device("tok-a", users["a"])
    fcm.status = 500
    raw = today_alert()
    assert ingest(user_id, raw, "gmail", "gmail:falla", received_ms=1) == "stored"
    assert len(fcm.sent) == 1
    # El correo queda extraído y el movimiento reclamado: el aviso se pierde, nunca sale doble.
    assert _email_and_movements(user_id) == (["extracted"], [True])
    fcm.status = 200
    assert (
        ingest(user_id, raw, "gmail", "gmail:falla") == "duplicate"
    )  # reintento de Pub/Sub
    assert push.new_movements(user_id) == 0
    assert len(fcm.sent) == 1


@requires_local
def test_an_error_while_notifying_still_marks_the_email(env, users, fcm, monkeypatch):
    user_id, _ = env

    def boom(*a, **kw):
        raise httpx.ConnectError("caído")

    monkeypatch.setattr(push, "_device_tokens", boom)
    assert ingest(user_id, today_alert(), "gmail", "gmail:error") == "stored"
    # Sin reclamar: el próximo correo avisará este movimiento.
    assert _email_and_movements(user_id) == (["extracted"], [False])
    monkeypatch.undo()
    monkeypatch.setattr(settings, "fcm_credentials_file", "simulado.json")
    monkeypatch.setattr(push, "_post", fcm)
    device("tok-a", users["a"])
    assert push.new_movements(user_id) == 1


@requires_local
def test_the_notice_goes_out_before_marking_the_email(env, monkeypatch):
    user_id, _ = env
    seen = []
    monkeypatch.setattr(
        push,
        "new_movements",
        lambda *a, **kw: seen.append(_email_and_movements(user_id)[0]),
    )
    assert ingest(user_id, today_alert(), "gmail", "gmail:orden") == "stored"
    assert seen == [
        ["pending_extraction"]
    ]  # el movimiento ya existe; el correo, aún sin marcar
    assert _email_and_movements(user_id)[0] == ["extracted"]


@requires_local
def test_the_notice_logs_each_stretch_without_content(env, users, fcm, caplog):
    caplog.set_level(logging.INFO, logger="fsf.push")
    user_id, _ = env
    device("tok-a", users["a"])
    token = push.PUBSUB_TIMES.set((1000, 2000))
    try:
        ingest(user_id, today_alert(), "gmail", "gmail:tramos", received_ms=500)
    finally:
        push.PUBSUB_TIMES.reset(token)
    [line] = [r.getMessage() for r in caplog.records if "tramos" in r.getMessage()]
    assert re.fullmatch(
        r"tramos correo=500 publicado=1000 llegada=2000 guardado=\d+ fcm=\d+ "
        r"tipo=gasto_registrado",
        line,
    )


@requires_local
def test_supabase_errors_do_not_carry_the_filters_into_the_logs():
    from app import service_db

    with pytest.raises(httpx.HTTPStatusError) as e:
        service_db.rest(
            "GET",
            "gmail_connections",
            params={
                "gmail_address": "eq.persona.privada@gmail.com",
                "select": "noexiste",
            },
        )
    assert str(e.value) == "Supabase GET gmail_connections respondió 400"


@requires_local
def test_the_whole_flow_logs_no_personal_data(env, users, fcm, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    user_id, _ = env
    device("tok-secreto-a", users["a"])
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(llm, "ask_category", lambda merchant, names: None)
    gmail_address = svc(
        "GET", f"gmail_connections?user_id=eq.{user_id}&select=gmail_address"
    )[0]["gmail_address"]
    ingest(user_id, today_alert(), "gmail", "gmail:logs", received_ms=1)
    categorize.run_pending(user_id, ask=True)
    assert len(fcm.sent) >= 1  # hubo avisos
    for secret in (
        MERCHANT,
        "SUPERMERCADO",
        "45.900",
        "45900",
        "*1111",
        gmail_address,
        users["a"]["email"],
        "tok-secreto-a",
        "Registramos",  # el texto del aviso tampoco
    ):
        assert secret not in caplog.text, secret


@requires_local
def test_cash_invoice_notice_says_it_was_counted_in_the_withdrawal(env, users, fcm):
    user_id, _ = env
    device("tok-a", users["a"])
    tx(user_id, "15800", counts_in_budget=False, payment_method="cash")
    assert push.new_movements(user_id) == 1
    assert fcm.sent[0][1]["body"] == (
        f"Registramos tu factura de {cop(Decimal(15800))} en efectivo. Ya estaba contada en tu retiro."
    )


@requires_local
def test_unknown_category_is_asked_once_and_disappears_when_chosen(
    env, users, fcm, monkeypatch
):
    user_id, _ = env
    a = users["a"]
    device("tok-a", a)
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    # No la sabe: elige «Otros» (igual que si no respondiera ninguna).
    monkeypatch.setattr(llm, "ask_category", lambda merchant, names: "Otros")
    other = svc("GET", "categories?name=eq.Otros&user_id=is.null&select=id")[0]["id"]
    pending = {"category_id": other, "category_source": "pendiente"}
    t = tx(user_id, "45500", merchant="ESTACION DE SERVICIO EJEMPLO", **pending)
    tx(user_id, "9000", status="pending_review", merchant="OTRO COMERCIO", **pending)

    assert categorize.run_pending(user_id) == 2  # el backfill no pregunta
    assert fcm.sent == []
    svc("PATCH", f"transactions?id=eq.{t['id']}", json={"category_source": "pendiente"})
    assert categorize.run_pending(user_id, ask=True) == 1
    # Solo el gasto confirmado; el por confirmar ya tiene su aviso y su hoja.
    assert [(d["tipo"], d["transaction_id"]) for _, d in fcm.sent] == [
        (push.CATEGORY, t["id"])
    ]
    assert fcm.sent[0][1]["title"] == "¿En qué categoría va este gasto?"
    categorize._ask(user_id, {**t, "direction": "expense", "status": "confirmed"})
    assert len(fcm.sent) == 1  # una sola pregunta por movimiento

    def asked():
        r = client.get(f"/transactions/{t['id']}", headers=bearer(a["token"]))
        return r.json()["preguntar_categoria"]

    assert asked() is True
    food = svc("GET", "categories?name=eq.Alimentos&user_id=is.null&select=id")[0]["id"]
    r = client.patch(
        f"/transactions/{t['id']}/category",
        headers=bearer(a["token"]),
        json={"category_id": food},
    )
    assert r.status_code == 200
    assert asked() is False
    rules = svc("GET", f"category_rules?user_id=eq.{user_id}&select=merchant_key")
    assert rules == [
        {"merchant_key": "ESTACION DE SERVICIO EJEMPLO"}
    ]  # regla del Paso 10


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
def test_an_html_404_does_not_delete_the_token(env, users, fcm):
    # Un FCM_PROJECT_ID mal puesto da 404 en HTML: el token sigue siendo bueno.
    user_id, _ = env
    device("tok-bueno", users["a"])
    fcm.status = 404
    fcm.html = True
    tx(user_id, "10000")
    assert push.new_movements(user_id) == 0
    assert svc("GET", "device_tokens?token=eq.tok-bueno&select=token") == [
        {"token": "tok-bueno"}
    ]


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
