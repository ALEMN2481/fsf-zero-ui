"""Paso 13, integración contra Supabase LOCAL: /coach con el motor real y el LLM simulado."""

from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import test_daily_api
from fastapi.testclient import TestClient
from local_supabase import ANON, URL, bearer, requires_local
from test_extract_store import SERVICE, svc

from app import coach
from app.config import settings
from app.extract.bancolombia import COLOMBIA
from app.main import app

pytestmark = requires_local
client = TestClient(app)
tx = test_daily_api.tx


@pytest.fixture
def setup(users, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE)
    monkeypatch.setattr(settings, "ollama_url", "http://llm.simulado")
    a = users["a"]
    r = client.post("/budgets", headers=bearer(a["token"]), json={"amount": "3000000"})
    assert r.status_code == 201, r.text
    tx(a["id"], "45000")
    return a


def llm_says(monkeypatch, reply):
    def fake(system, prompt):
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(coach, "ask_llm", fake)


def ask(token, text):
    r = client.post("/coach", headers=bearer(token), json={"mensaje": text})
    assert r.status_code == 200, r.text
    return r.json()


def gps(token):
    return client.get("/gps", headers=bearer(token)).json()


def figures(reply):
    return [p["texto"] for p in reply["partes"] if p["cifra"]]


def test_the_figures_are_the_engine_ones(setup, monkeypatch):
    token = setup["token"]
    llm_says(monkeypatch, "Hoy puedes gastar {disponible_hoy}.")
    reply = ask(token, "¿Cuánto puedo gastar hoy?")
    today = Decimal(gps(token)["disponible_hoy"])
    assert (reply["fuente"], reply["tipo"]) == ("llm", "hoy")
    assert figures(reply) == [coach.cop(today)]

    llm_says(
        monkeypatch, "Hoy puedes gastar 9.999.999."
    )  # el LLM intenta colar una cifra
    reply = ask(token, "¿Cuánto puedo gastar hoy?")
    assert reply["fuente"] == "plantilla"
    assert figures(reply) == [coach.cop(today)]


def test_history_is_stored_with_markers_and_shown_as_it_was(setup, monkeypatch):
    token, user_id = setup["token"], setup["id"]
    llm_says(monkeypatch, httpx.ConnectError("caído"))
    first = ask(token, "¿Cuánto puedo gastar hoy?")
    rows = svc(
        "GET", f"coach_messages?user_id=eq.{user_id}&select=role,content,source,valores"
    )
    assistant = next(r for r in rows if r["role"] == "assistant")
    assert (
        "{disponible_hoy}" in assistant["content"] and "$" not in assistant["content"]
    )
    assert assistant["source"] == "plantilla" and set(assistant["valores"]) == {
        "disponible_hoy"
    }

    tx(user_id, "10000")  # las cifras cambian: el mensaje antiguo se ve como fue
    history = client.get("/coach/messages", headers=bearer(token)).json()
    assert [m["rol"] for m in history] == ["user", "assistant"]
    assert history[1]["partes"] == first["partes"]


def test_retention_privacy_and_clearing(setup, users, monkeypatch):
    token, user_id = setup["token"], setup["id"]
    old = (datetime.now(COLOMBIA) - timedelta(days=91)).isoformat()
    svc(
        "POST",
        "coach_messages",
        json={
            "user_id": user_id,
            "role": "user",
            "content": "viejo",
            "created_at": old,
        },
    )
    llm_says(monkeypatch, httpx.ConnectError("caído"))
    ask(token, "Hola")
    contents = [
        r["content"]
        for r in svc("GET", f"coach_messages?user_id=eq.{user_id}&select=content")
    ]
    assert (
        "viejo" not in contents and len(contents) == 2
    )  # lo de más de 90 días se borra

    other = users["b"]["token"]
    assert client.get("/coach/messages", headers=bearer(other)).json() == []
    # Nadie escribe mensajes «del Coach» por PostgREST (D15).
    r = httpx.post(
        f"{URL}/rest/v1/coach_messages",
        headers={"apikey": ANON, **bearer(token)},
        json={
            "user_id": user_id,
            "role": "assistant",
            "content": "Tienes $ 1",
            "source": "llm",
        },
    )
    assert r.status_code in (401, 403), r.text

    assert client.delete("/coach/messages", headers=bearer(token)).status_code == 204
    assert client.get("/coach/messages", headers=bearer(token)).json() == []


def test_simulating_then_spending_gives_the_same_figures(setup, monkeypatch):
    token, user_id = setup["token"], setup["id"]
    llm_says(monkeypatch, "Te quedarían {sim_saldo_libre} en el mes.")
    reply = ask(token, "¿Qué pasa si gasto $20.000 más hoy?")
    assert (reply["tipo"], reply["fuente"]) == ("simulacion", "llm")
    tx(user_id, "20000")
    assert figures(reply) == [coach.cop(Decimal(gps(token)["saldo_libre"]))]


def test_without_budget_it_invites_to_set_one(users, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE)
    llm_says(monkeypatch, "no se llama")
    reply = ask(users["b"]["token"], "¿Cuánto puedo gastar hoy?")
    assert (
        reply["fuente"] == "plantilla" and "presupuesto" in reply["partes"][0]["texto"]
    )


def test_message_is_validated(users):
    r = client.post(
        "/coach", headers=bearer(users["a"]["token"]), json={"mensaje": "x" * 501}
    )
    assert r.status_code == 422
