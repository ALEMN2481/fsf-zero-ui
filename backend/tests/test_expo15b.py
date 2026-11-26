"""Paso 15B: gráfico de la semana (`/gps` → semana_dias) y gasto en efectivo agregado a mano."""

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from local_supabase import bearer, requires_local
from test_daily_api import client, get, post, tx
from test_extract_store import svc

from app import main
from app.engine import gps
from app.engine.gps import CASH_INVOICE, REFUND, SPENDING, Movement
from app.extract.bancolombia import COLOMBIA

D = Decimal
WED = date(2026, 11, 25)


def mv(day, amount, kind=SPENDING):
    return Movement(day, D(amount), kind, "Alimentos")


# ---------------------------------------------------------------- week_by_day (sin BD)
def test_week_by_day_goes_monday_to_sunday_with_net_spending():
    moves = [
        mv(date(2026, 11, 22), "999"),  # domingo anterior: no cuenta
        mv(date(2026, 11, 23), "32000"),
        mv(date(2026, 11, 23), "2000", REFUND),  # devolución del mismo día
        mv(date(2026, 11, 24), "10000"),
        mv(
            date(2026, 11, 24), "15000", REFUND
        ),  # más devolución que gasto: 0, no negativo
        mv(date(2026, 11, 25), "23500"),
        mv(date(2026, 11, 25), "9500", CASH_INVOICE),  # ya contado en el retiro
    ]
    days = gps.week_by_day(moves, WED)
    assert [d for d, _ in days] == [date(2026, 11, 23 + i) for i in range(7)]
    assert [v for _, v in days] == [
        D("30000.00"),
        D("0.00"),
        D("23500.00"),
        *[D("0.00")] * 4,
    ]


def test_week_by_day_on_a_sunday_and_a_monday():
    sunday, monday = date(2026, 11, 29), date(2026, 11, 30)
    assert gps.week_by_day([mv(sunday, "5")], sunday)[-1] == (sunday, D("5.00"))
    assert gps.week_by_day([mv(sunday, "5")], monday)[0] == (monday, D("0.00"))


# ---------------------------------------------------------------- /gps (Supabase local)
@requires_local
def test_gps_has_the_seven_days_of_the_week(users):
    a = users["a"]
    assert post("/budgets", a["token"], {"amount": "3000000"}).status_code == 201
    tx(a["id"], "45900")
    state = get("/gps", a["token"])
    days = state["semana_dias"]
    today = datetime.now(COLOMBIA).date().isoformat()
    assert len(days) == 7
    assert next(d for d in days if d["fecha"] == today)["gastado"] == "45900.00"


@requires_local
def test_the_week_includes_days_before_the_budget_period(users, monkeypatch):
    # Miércoles 2 de diciembre: la semana empezó el lunes 30 de noviembre, en otro periodo.
    monkeypatch.setattr(main, "_today", lambda: date(2026, 12, 2))
    a = users["a"]
    assert post("/budgets", a["token"], {"amount": "3000000"}).status_code == 201
    tx(a["id"], "12000", when=datetime.combine(date(2026, 11, 30), time(10), COLOMBIA))
    days = get("/gps", a["token"])["semana_dias"]
    assert days[0] == {"fecha": "2026-11-30", "gastado": "12000.00"}


# ---------------------------------------------------------------- gasto a mano
def category(name):
    return svc("GET", f"categories?name=eq.{name}&user_id=is.null&select=id")[0]["id"]


@requires_local
def test_a_cash_expense_from_a_withdrawal_does_not_lower_the_budget(users):
    a = users["a"]
    post("/budgets", a["token"], {"amount": "3000000"})
    before = get("/gps", a["token"])["disponible_hoy"]
    r = post(
        "/transactions",
        a["token"],
        {
            "monto": "12500",
            "category_id": category("Alimentos"),
            "comercio": "  Panaderia   del barrio ",
        },
    )
    assert r.status_code == 201, r.text
    moved = r.json()
    assert (moved["monto"], moved["comercio"], moved["categoria"], moved["tipo"]) == (
        "12500.00",
        "Panaderia del barrio",
        "Alimentos",
        CASH_INVOICE,  # «efectivo, ya contado en el retiro»
    )
    assert (
        get("/gps", a["token"])["disponible_hoy"] == before
    )  # D12: ya se contó en el retiro
    [row] = svc(
        "GET",
        f"transactions?id=eq.{moved['id']}&select=source,status,payment_method,counts_in_budget,"
        "category_source,notified_at,direction",
    )
    assert row["source"] == "manual" and row["payment_method"] == "cash"
    assert row["status"] == "confirmed" and row["direction"] == "expense"
    assert row["counts_in_budget"] is False and row["category_source"] == "usuario"
    assert row["notified_at"]  # no sale aviso push: lo agregó el propio usuario
    # Aprende la regla del comercio (Paso 10).
    assert svc("GET", f"category_rules?user_id=eq.{a['id']}&select=merchant_key") == [
        {"merchant_key": "PANADERIA DEL BARRIO"}
    ]


@requires_local
def test_not_from_a_withdrawal_it_counts_in_the_budget(users):
    a = users["a"]
    post("/budgets", a["token"], {"amount": "3000000"})
    before = D(get("/gps", a["token"])["disponible_hoy"])
    r = post(
        "/transactions",
        a["token"],
        {"monto": "20000", "category_id": category("Otros"), "fuera_de_retiro": True},
    )
    assert r.status_code == 201, r.text
    assert r.json()["tipo"] == SPENDING and r.json()["comercio"] is None
    assert D(get("/gps", a["token"])["disponible_hoy"]) == before - D("20000")
    assert svc("GET", f"category_rules?user_id=eq.{a['id']}&select=merchant_key") == []


@requires_local
@pytest.mark.parametrize(
    "body",
    [
        {"monto": "0"},
        {"monto": "-5000"},
        {"monto": "1234567890123.00"},  # 15 dígitos: no cabe en numeric(14, 2)
        {"monto": "10.555"},
        {"monto": "5000", "comercio": "x" * 61},
    ],
)
def test_invalid_amounts_or_merchant_are_refused(users, body):
    r = post(
        "/transactions", users["a"]["token"], {"category_id": category("Otros"), **body}
    )
    assert r.status_code == 422


@requires_local
def test_income_or_someone_elses_category_is_refused_and_b_cannot_see_it(users):
    a, b = users["a"], users["b"]
    r = post(
        "/transactions",
        a["token"],
        {"monto": "5000", "category_id": category("Ingresos")},
    )
    assert r.status_code == 422  # solo gastos
    own = svc(
        "POST",
        "categories",
        json={"user_id": b["id"], "name": "Mascotas de B"},
        headers={"Prefer": "return=representation"},
    )[0]["id"]
    r = post("/transactions", a["token"], {"monto": "5000", "category_id": own})
    assert r.status_code == 422  # RLS: A no ve las categorías propias de B
    created = post(
        "/transactions", a["token"], {"monto": "5000", "category_id": category("Otros")}
    )
    r = client.get(f"/transactions/{created.json()['id']}", headers=bearer(b["token"]))
    assert r.status_code == 404
