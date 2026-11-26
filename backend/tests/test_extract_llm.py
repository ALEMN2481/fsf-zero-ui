"""Paso 09C: respaldo con LLM local. Ollama simulado: la CI nunca llama a un modelo."""

import json
import threading
import time
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.extract import llm
from app.extract.bancolombia import COLOMBIA

TEXT = (
    "Bancolombia: realizaste una compra de $15.000,00 en PAPELERIA FICTICIA usando tu tarjeta "
    "debito *0000 el 20/11/2026 a las 16:20. Inquietudes al 604 510 9000."
)
RECEIVED = datetime(2026, 11, 20, 16, 21, tzinfo=COLOMBIA)
GOOD = {
    "amount": "$15.000,00",
    "direction": "expense",
    "merchant": "PAPELERIA FICTICIA",
    "date": "20/11/2026",
    "time": "16:20",
    "payment_method": "debit_card",
    "last4": "0000",
}


def check(text=TEXT, received=RECEIVED, **changes):
    return llm.check(text, json.dumps({**GOOD, **changes}), received)


def test_valid_answer_goes_to_review_never_confirmed():
    a = check()
    assert a.status == "pending_review" and a.template == "llm"
    assert (a.amount, a.merchant, a.payment_method, a.last4) == (
        Decimal("15000.00"),
        "PAPELERIA FICTICIA",
        "debit_card",
        "0000",
    )
    assert a.occurred_at == datetime(2026, 11, 20, 16, 20, tzinfo=COLOMBIA)


@pytest.mark.parametrize(
    "changes, reason",
    [
        (
            {"amount": "$16.000,00"},
            "monto_no_coincide",
        ),  # monto que no está en el texto
        ({"amount": "15000.5"}, "monto_no_coincide"),
        ({"amount": "quince mil"}, "monto"),
        ({"amount": 15000}, "esquema"),  # número y no texto
        ({"direction": "gasto"}, "esquema"),
        ({"payment_method": "nequi"}, "esquema"),
        ({"time": "null"}, "esquema"),  # lo que escribía llama3.2:3b sin hora
        ({"extra": "x"}, "esquema"),  # campos de más
        ({"last4": "9999"}, "last4"),  # no aparece tras un *
        ({"merchant": "TIENDA INVENTADA POR EL MODELO"}, "comercio"),
        ({"date": "31/02/2026"}, "fecha"),
        ({"date": "20/10/2026"}, "fecha"),  # a más de 3 días de la recepción
    ],
)
def test_answers_that_fail_a_check_are_rejected(changes, reason):
    a = check(**changes)
    assert (a.status, a.reason, a.amount) == ("failed", reason, None)


def test_missing_field_or_broken_json_is_rejected():
    raw = json.dumps({k: v for k, v in GOOD.items() if k != "last4"})
    assert llm.check(TEXT, raw, RECEIVED).reason == "esquema"
    assert llm.check(TEXT, "{no es json", RECEIVED).reason == "esquema"


def test_text_with_two_amounts_or_foreign_currency_is_rejected():
    assert check(TEXT + " Saldo disponible $1.200.000,00.").reason == "varios_montos"
    usd = TEXT.replace("$15.000,00", "USD15,00")
    assert (
        llm.check(usd, json.dumps({**GOOD, "amount": "15,00"}), RECEIVED).reason
        == "moneda"
    )


def test_null_fields_are_allowed():
    a = check(merchant=None, time=None, last4=None)
    assert a.status == "pending_review" and a.merchant is None and a.last4 is None


# ---------------------------------------------------------------- llamada a Ollama
@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(settings, "ollama_keep_alive", "45m")
    calls = []

    def post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        if "fail" in calls[0][1].get("prompt", ""):
            raise httpx.ConnectError("caído")
        body = {"response": __import__("json").dumps(GOOD)} if "prompt" in json else {}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    return calls


def test_request_uses_schema_temperature_zero_and_keep_alive(ollama):
    a = llm.extract(TEXT, RECEIVED)
    assert a.status == "pending_review"
    url, body, timeout = ollama[0]
    assert url == "http://ollama.test/api/generate"
    assert body["model"] == settings.ollama_model == "qwen2.5:3b"
    assert body["options"] == {"temperature": 0} and body["keep_alive"] == "45m"
    assert body["format"] == llm.SCHEMA and body["stream"] is False
    assert "Alerta: " in body["prompt"] and "JSON:" in body["prompt"]
    assert timeout == settings.ollama_timeout


def test_ollama_down_or_disabled_never_raises(ollama, monkeypatch):
    assert llm.extract("fail " + TEXT, RECEIVED).reason == "llm_no_disponible"
    monkeypatch.setattr(settings, "ollama_url", "")
    assert llm.extract(TEXT, RECEIVED).reason == "llm_desactivado"


def test_preload_loads_the_model_without_a_prompt(ollama):
    llm.preload()
    assert ollama[-1][1] == {"model": "qwen2.5:3b", "keep_alive": "45m"}


def test_preload_tolerates_missing_ollama(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:9")  # nadie escucha
    monkeypatch.setattr(settings, "ollama_timeout", 2)
    llm.preload()  # no lanza
    assert "no se pudo precargar el modelo" in caplog.text


def test_backend_starts_without_waiting_for_the_preload(monkeypatch):
    from app import gmail, service_db
    from app.main import app

    # El lifespan cambia y cierra los clientes HTTP compartidos: se restauran al terminar.
    monkeypatch.setattr(service_db, "http", service_db.http)
    monkeypatch.setattr(gmail, "http", gmail.http)
    release = threading.Event()
    monkeypatch.setattr(llm, "preload", lambda: release.wait(10))
    start = time.perf_counter()
    with TestClient(app) as client:  # ejecuta el lifespan
        assert client.get("/health").status_code == 200
        assert time.perf_counter() - start < 2  # no esperó los 10 s de la precarga
    release.set()
    assert service_db.http.is_closed and gmail.http.is_closed  # se cierran al apagar
