"""Paso 12, integración contra Supabase LOCAL: API de la pantalla «Disponible diario»."""

from datetime import datetime, timedelta
from decimal import Decimal

import test_extract_store
from fastapi.testclient import TestClient
from local_supabase import bearer, requires_local
from test_extract_store import alert_email, svc

from app.engine.gps import month_bounds
from app.extract.bancolombia import COLOMBIA
from app.ingest.store import ingest
from app.main import app

pytestmark = requires_local
env = test_extract_store.env  # usuario A con Gmail y cuenta *1111
client = TestClient(app)
TODAY = datetime.now(COLOMBIA).date()
MONTH_START, MONTH_END = month_bounds(TODAY)


def get(path, token):
    r = client.get(path, headers=bearer(token))
    assert r.status_code == 200, r.text
    return r.json()


def post(path, token, body=None):
    return client.post(path, headers=bearer(token), json=body)


def tx(user_id, amount, direction="expense", status="confirmed", when=None, **extra):
    """Movimiento manual vía service_role, con fecha en hora de Colombia."""
    when = when or datetime.now(COLOMBIA)
    return svc(
        "POST",
        "transactions",
        json={
            "user_id": user_id,
            "direction": direction,
            "amount": amount,
            "occurred_at": when.isoformat(),
            "source": "manual",
            "status": status,
            **extra,
        },
        headers={"Prefer": "return=representation"},
    )[0]


def test_budget_with_one_field_is_the_current_month_and_can_change(users):
    token = users["a"]["token"]
    r = post("/budgets", token, {"amount": "2000000"})
    assert r.status_code == 201, r.text
    assert (r.json()["period_start"], r.json()["period_end"]) == (
        MONTH_START.isoformat(),
        MONTH_END.isoformat(),
    )
    r = post("/budgets", token, {"amount": "2500000.50"})
    assert (
        r.status_code == 200 and r.json()["amount"] == "2500000.50"
    )  # cambia el monto
    assert get("/gps", token)["periodo"]["presupuesto"] == "2500000.50"
    r = post("/budgets", token, {"amount": "1", "period_start": "2026-01-01"})
    assert r.status_code == 422


def test_budget_renews_itself_with_the_same_amount(users):
    token = users["a"]["token"]
    last_start, last_end = month_bounds(MONTH_START - timedelta(days=1))
    body = {
        "amount": "1200000",
        "period_start": str(last_start),
        "period_end": str(last_end),
    }
    assert post("/budgets", token, body).status_code == 201
    s = get("/gps", token)
    assert s["estado"] == "ok"
    assert s["periodo"] == {
        "inicio": MONTH_START.isoformat(),
        "fin": MONTH_END.isoformat(),
        "presupuesto": "1200000.00",
        "renovado": True,
    }
    # Escribir el monto del mes en curso crea su periodo, que deja de ser renovado.
    assert post("/budgets", token, {"amount": "1300000"}).status_code == 201
    assert get("/gps", token)["periodo"]["renovado"] is False


def test_suggestion_is_last_month_spending_with_income_as_reference(env, users):
    user_id, _ = env
    token = users["a"]["token"]
    assert get("/budgets/suggestion", token) == {
        "gasto_mes_anterior": "0.00",
        "ingresos_mes_anterior": "0.00",
        "sugerido": None,  # sin gasto previo: el campo queda vacío
    }
    income = svc(
        "GET",
        "categories",
        params={"name": "eq.Ingresos", "user_id": "is.null", "select": "id"},
    )[0]["id"]
    last_month = datetime.combine(
        MONTH_START - timedelta(days=3), datetime.min.time(), COLOMBIA
    )
    tx(user_id, "700000.00", when=last_month)
    tx(user_id, "3000000.00", "income", when=last_month, category_id=income)
    tx(user_id, "999.00")  # de este mes: no cuenta
    assert get("/budgets/suggestion", token) == {
        "gasto_mes_anterior": "700000.00",
        "ingresos_mes_anterior": "3000000.00",
        "sugerido": "700000.00",
    }


def test_movements_confirm_and_dismiss(env, users):
    user_id, _ = env
    a, b = users["a"]["token"], users["b"]["token"]
    assert post("/budgets", a, {"amount": "1000000"}).status_code == 201
    pending = tx(
        user_id, "10000.00", status="pending_review", merchant="TIENDA EJEMPLO"
    )
    other = tx(user_id, "20000.00", status="pending_review", merchant="OTRA EJEMPLO")
    assert ingest(user_id, alert_email("A01")) == "stored"

    listed = {m["comercio"]: m for m in get("/movements", a)}
    assert (listed["TIENDA EJEMPLO"]["estado"], listed["TIENDA EJEMPLO"]["tipo"]) == (
        "pending_review",
        "gasto",
    )
    assert listed["PANADERIA EJEMPLO"]["categoria"] == "Alimentos"
    assert all(isinstance(m["monto"], str) for m in listed.values())  # nunca float
    assert get("/gps", a)["en_revision"] == "30000.00"

    assert post(f"/transactions/{pending['id']}/confirm", b).status_code == 404
    r = post(f"/transactions/{pending['id']}/confirm", a)
    assert r.status_code == 200 and r.json()["estado"] == "confirmed"
    assert post(f"/transactions/{pending['id']}/dismiss", a).status_code == 409

    before = Decimal(get("/gps", a)["gasto_periodo"])
    assert post(f"/transactions/{other['id']}/dismiss", a).status_code == 200
    s = get("/gps", a)
    assert s["en_revision"] == "0.00"
    assert before - Decimal(s["gasto_periodo"]) == Decimal("20000.00")
    assert "OTRA EJEMPLO" not in {m["comercio"] for m in get("/movements", a)}
    assert svc(
        "GET", "transactions", params={"id": f"eq.{other['id']}", "select": "status"}
    ) == [{"status": "dismissed"}]  # queda registro: no se borra
    assert get("/movements", b) == []
