"""Paso 11, integración contra Supabase LOCAL: /gps, presupuestos y bolsillos con el JWT del usuario."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import test_extract_store
from fastapi.testclient import TestClient
from local_supabase import bearer, requires_local
from test_extract_store import alert_email, invoice_email, svc

from app.extract.bancolombia import COLOMBIA
from app.ingest.store import ingest
from app.main import app

pytestmark = requires_local
env = test_extract_store.env  # fixture compartida: usuario A con Gmail y cuenta *1111
client = TestClient(app)

TODAY = datetime.now(COLOMBIA).date()
# Contiene las fechas del conjunto del supervisor (noviembre de 2026) y hoy.
PERIOD = {
    "period_start": "2026-11-01",
    "period_end": (max(TODAY, date(2026, 11, 30)) + timedelta(days=30)).isoformat(),
    "amount": "1000000.00",
}


def gps(token):
    r = client.get("/gps", headers=bearer(token))
    assert r.status_code == 200, r.text
    return r.json()


def budget(token, **changes):
    return client.post("/budgets", headers=bearer(token), json={**PERIOD, **changes})


def test_atm_withdrawal_and_cash_invoice_are_one_expense(env, users):
    user_id, _ = env
    a = users["a"]
    assert budget(a["token"]).status_code == 201
    assert ingest(user_id, alert_email("A05")) == "stored"  # retiro de $200.000
    assert (
        ingest(user_id, invoice_email("F02")) == "stored"
    )  # factura en efectivo de $32.000

    s = gps(a["token"])
    assert s["estado"] == "ok"
    assert (
        s["gasto_periodo"] == "200000.00"
    )  # no 232.000: el efectivo ya salió con el retiro
    by_category = {c["categoria"]: c for c in s["por_categoria"]}
    assert by_category["Alimentos"]["efectivo_factura"] == "32000.00"
    assert by_category["Otros"]["gasto"] == "200000.00"
    assert all(
        isinstance(v, str) for v in (s["saldo_libre"], s["cuota_hoy"])
    )  # nunca float


def test_transfer_to_an_own_account_is_not_an_expense(env, users):
    user_id, _ = env
    a = users["a"]
    assert budget(a["token"]).status_code == 201
    assert ingest(user_id, alert_email("A06")) == "stored"  # $150.000 a la cuenta *9999
    assert (
        gps(a["token"])["gasto_periodo"] == "150000.00"
    )  # *9999 no es del usuario: gasto

    svc(
        "POST",
        "accounts",
        json={"user_id": user_id, "name": "Ahorros", "kind": "debit", "last4": "9999"},
    )
    assert gps(a["token"])["gasto_periodo"] == "0.00"  # ahora es entre cuentas propias


def test_budgets_are_per_user_and_cannot_overlap(env, users):
    a, b = users["a"], users["b"]
    assert gps(a["token"])["estado"] == "sin_presupuesto"
    assert budget(a["token"]).status_code == 201
    assert budget(a["token"], amount="5.00").status_code == 409  # mismo periodo
    assert budget(a["token"], period_end="2026-10-01").status_code == 422
    assert budget(a["token"], amount="-1.00").status_code == 422
    assert gps(b["token"])["estado"] == "sin_presupuesto"  # B no ve el presupuesto de A
    assert client.get("/gps").status_code == 401


def test_pocket_overdraft_returns_the_maximum(env, users):
    user_id, _ = env
    a, b = users["a"], users["b"]
    pocket = client.post("/pockets", headers=bearer(a["token"]), json={"name": "Viaje"})
    assert pocket.status_code == 201, pocket.text
    url = f"/pockets/{pocket.json()['id']}/movements"

    def move(amount, token=a["token"]):
        return client.post(url, headers=bearer(token), json={"amount": amount})

    r = move("1000.00")  # sin presupuesto no hay saldo libre del que apartar
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "sin_presupuesto"

    assert budget(a["token"]).status_code == 201
    assert ingest(user_id, alert_email("A05")) == "stored"  # gasto de $200.000
    r = move("900000.00")  # CU-05 A1: más que el saldo libre
    assert r.status_code == 409
    assert r.json()["detail"] == {"motivo": "sobregiro", "maximo": "800000.00"}

    assert move("800000.00").status_code == 201  # justo el máximo
    assert gps(a["token"])["saldo_libre"] == "0.00"
    r = move("-800000.01")
    assert r.status_code == 409
    assert r.json()["detail"] == {"motivo": "saldo_insuficiente", "maximo": "800000.00"}
    r = move("-300000.00")
    assert r.status_code == 201 and r.json()["saldo"] == "500000.00"
    assert Decimal(gps(a["token"])["saldo_libre"]) == Decimal("300000.00")

    assert move("1.00", b["token"]).status_code == 404  # B no usa el bolsillo de A
    [p] = client.get("/pockets", headers=bearer(a["token"])).json()
    assert (p["name"], p["saldo"]) == ("Viaje", "500000.00")
    assert client.get("/pockets", headers=bearer(b["token"])).json() == []
