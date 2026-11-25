"""Paso 11: motor GPS con funciones puras. Un test por fórmula, casos borde y propiedades."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.gps import (
    CASH_INVOICE,
    EARNING,
    OWN_TRANSFER,
    REFUND,
    REFUND_IN_REVIEW,
    SPENDING,
    Budget,
    Movement,
    classify,
    month_bounds,
    reference,
    renew,
    split,
    summary,
)

D = Decimal
NOV = Budget(date(2026, 11, 1), date(2026, 11, 30), D("3000000.00"))
WED = date(
    2026, 11, 25
)  # miércoles: quedan 6 días (25..30) y la semana termina el domingo 29


def spend(day, amount, category="Alimentos", kind=SPENDING, in_review=False):
    return Movement(day, D(amount), kind, category, in_review)


def state(movements=(), pockets=(), today=WED, budget=NOV):
    return summary(budget, today, list(movements), list(pockets))


# ---------------------------------------------------------------- reparto
def test_split_whole_pesos_and_remainder_to_last_day():
    assert split(D("100000.00"), 3) == [D("33333.00"), D("33333.00"), D("33334.00")]
    assert split(D("10.55"), 4) == [D("2.00"), D("2.00"), D("2.00"), D("4.55")]
    assert split(D("5.00"), 1) == [D("5.00")]


@pytest.mark.parametrize("total", [D("0.00"), D("-500.00")])
def test_split_nothing_or_negative_gives_zeros(total):
    assert split(total, 3) == [D("0.00")] * 3


# ---------------------------------------------------------------- fórmulas
def test_free_balance_daily_and_weekly():
    s = state(
        [
            spend(date(2026, 11, 10), "1200000.00"),
            spend(WED, "20000.00"),
        ],
        pockets=[(date(2026, 11, 5), D("200000.00"))],
    )
    # L₀ = 3.000.000 − 1.200.000 − 200.000 = 1.600.000; 6 días → 266.666 por día (+4 el último)
    assert s["saldo_libre"] == D("1580000.00")  # L = L₀ − Gh
    assert s["gasto_periodo"] == D("1220000.00")
    assert s["apartado_periodo"] == D("200000.00")
    assert s["dias_restantes"] == 6
    assert s["cuota_hoy"] == D("266666.00")
    assert s["disponible_hoy"] == D("246666.00")
    assert s["exceso"] == D("0.00")
    assert s["disponible_semana"] == D("266666.00") * 5 - D("20000.00")  # mié..dom
    assert s["maximo_apartable"] == D("1580000.00")


def test_overspending_recalculates_the_rest_of_the_period():
    """Efecto GPS: un gasto fuera de plan baja el diario de los días siguientes."""
    s = state([spend(WED, "566666.00")])  # L₀ = 3.000.000, cuota 500.000
    assert s["cuota_hoy"] == D("500000.00")
    assert s["disponible_hoy"] == D("-66666.00")  # negativo, no 0 (D12)
    assert s["exceso"] == D("66666.00")
    assert s["diario_plan"] == D("500000.00")  # lo que habría sido sin el exceso
    assert s["diario_desde_manana"] == D("486666.00")  # 2.433.334 / 5


def test_refund_subtracts_from_its_category_not_income():
    s = state(
        [
            spend(date(2026, 11, 3), "100000.00", "Alimentos"),
            spend(date(2026, 11, 4), "30000.00", "Alimentos", REFUND),
            spend(date(2026, 11, 4), "5000.00", "Alimentos", REFUND_IN_REVIEW),
            spend(date(2026, 11, 2), "4000000.00", "Ingresos", EARNING),
        ]
    )
    assert s["gasto_periodo"] == D("70000.00")
    assert s["ingresos_periodo"] == D("4000000.00")  # informativo: no suma al saldo
    assert s["saldo_libre"] == D("2930000.00")
    assert s["por_categoria"] == [
        {
            "categoria": "Alimentos",
            "gasto": D("70000.00"),
            "efectivo_factura": D("0.00"),
        }
    ]


def test_atm_withdrawal_and_cash_invoice_count_once():
    """Retiro de $200.000 + factura en efectivo de $32.000 → $200.000 de gasto, no $232.000."""
    s = state(
        [
            spend(date(2026, 11, 21), "200000.00", "Otros"),
            spend(date(2026, 11, 22), "32000.00", "Alimentos", CASH_INVOICE),
        ]
    )
    assert s["gasto_periodo"] == D("200000.00")
    assert {c["categoria"]: c for c in s["por_categoria"]}["Alimentos"] == {
        "categoria": "Alimentos",
        "gasto": D("0.00"),
        "efectivo_factura": D("32000.00"),  # queda para el detalle por categoría
    }


def test_in_review_expenses_count_and_are_reported():
    s = state([spend(WED, "10000.00", in_review=True), spend(WED, "5000.00")])
    assert s["gastado_hoy"] == D("15000.00")
    assert s["en_revision"] == D("10000.00")


def test_own_transfers_and_pocket_withdrawals():
    s = state(
        [spend(WED, "150000.00", "Otros", OWN_TRANSFER)],
        pockets=[(date(2026, 11, 2), D("100000.00")), (WED, D("-40000.00"))],
    )
    assert s["gasto_periodo"] == D("0.00")  # entre cuentas propias: no es gasto
    assert s["apartado_periodo"] == D("60000.00")  # retirar devuelve al saldo libre
    assert s["saldo_libre"] == D("2940000.00")


@pytest.mark.parametrize(
    "direction, status, category, counts, to_last4, expected",
    [
        ("expense", "confirmed", "Alimentos", True, None, SPENDING),
        ("expense", "pending_review", "Otros", True, None, SPENDING),
        ("expense", "confirmed", "Alimentos", False, None, CASH_INVOICE),
        ("expense", "confirmed", "Otros", True, "9999", OWN_TRANSFER),
        (
            "expense",
            "confirmed",
            "Otros",
            True,
            "1234",
            SPENDING,
        ),  # cuenta de otra persona
        ("income", "confirmed", "Ingresos", True, None, EARNING),
        ("income", "confirmed", None, True, None, EARNING),
        ("income", "confirmed", "Alimentos", True, None, REFUND),
        ("income", "pending_review", "Alimentos", True, None, REFUND_IN_REVIEW),
    ],
)
def test_classify(direction, status, category, counts, to_last4, expected):
    assert classify(direction, status, category, counts, to_last4, {"9999"}) == expected


# ---------------------------------------------------------------- casos borde
def test_no_budget_or_today_outside_the_period():
    assert state(budget=None)["estado"] == "sin_presupuesto"
    assert state(today=date(2026, 12, 1))["estado"] == "sin_presupuesto"


def test_last_day_of_the_period():
    s = state([spend(date(2026, 11, 29), "2900000.00")], today=date(2026, 11, 30))
    assert s["dias_restantes"] == 1
    assert s["cuota_hoy"] == D("100000.00") == s["disponible_semana"]
    assert s["diario_desde_manana"] is None and s["diario_plan"] is None


def test_week_is_cut_at_the_end_of_the_period():
    s = state(today=date(2026, 11, 30))  # lunes y último día: la semana es solo hoy
    assert s["disponible_semana"] == s["cuota_hoy"] == D("3000000.00")


def test_month_end_february_and_period_start():
    feb = Budget(date(2027, 2, 1), date(2027, 2, 28), D("280000.00"))
    s = state(budget=feb, today=date(2027, 2, 1))
    assert s["dias_restantes"] == 28 and s["cuota_hoy"] == D("10000.00")


def test_overspent_period_shows_negative_and_zero_quotas():
    s = state([spend(date(2026, 11, 20), "3100000.00")])
    assert s["saldo_libre"] == D("-100000.00")
    assert s["cuota_hoy"] == D("0.00") == s["diario_desde_manana"]
    assert s["disponible_hoy"] == D("0.00") and s["maximo_apartable"] == D("0.00")


def test_zero_budget_and_movements_outside_the_period():
    zero = Budget(NOV.start, NOV.end, D("0.00"))
    s = state([spend(date(2026, 10, 31), "999.00")], budget=zero)
    assert s["gasto_periodo"] == D("0.00") and s["cuota_hoy"] == D("0.00")


def test_future_dated_movement_counts_today():
    s = state([spend(date(2026, 11, 27), "10000.00")])
    assert s["gastado_hoy"] == D("10000.00")


# ---------------------------------------------------------------- propiedades
money = st.decimals(
    min_value=D("0.00"), max_value=D("999999999999.99"), places=2, allow_nan=False
)
signed = st.decimals(
    min_value=D("-999999999.99"),
    max_value=D("999999999999.99"),
    places=2,
    allow_nan=False,
)


@given(total=signed, days=st.integers(1, 366))
def test_split_properties(total, days):
    shares = split(total, days)
    assert len(shares) == days and all(s >= 0 for s in shares)
    assert all(s == s.quantize(D("0.01")) for s in shares)
    if total > 0:
        assert sum(shares) == total  # exacto: nada se pierde ni se inventa
        assert shares[0] * days <= total  # la cuota de hoy nunca supera la parte justa
        # todas menos la última: iguales y en pesos enteros
        assert len(set(shares[:-1])) <= 1 and all(s == int(s) for s in shares[:-1])
    else:
        assert sum(shares) == 0


movement = st.builds(
    lambda day, amount, kind: Movement(
        NOV.start + timedelta(days=day), amount, kind, "X"
    ),
    st.integers(0, 29),
    st.decimals(min_value=D("0.01"), max_value=D("5000000.00"), places=2),
    st.sampled_from([SPENDING, REFUND, EARNING, CASH_INVOICE]),
)


@given(
    amount=money,
    movements=st.lists(movement, max_size=20),
    today=st.integers(0, 29),
    extra=st.decimals(min_value=D("0.01"), max_value=D("5000000.00"), places=2),
)
def test_summary_properties(amount, movements, today, extra):
    budget = Budget(NOV.start, NOV.end, amount)
    day = NOV.start + timedelta(days=today)
    s = summary(budget, day, movements, [])
    days = s["dias_restantes"]
    l0 = s["saldo_libre"] + s["gastado_hoy"]
    # Lo repartido entre los días nunca supera lo disponible.
    assert s["cuota_hoy"] * days <= max(l0, 0)
    assert s["disponible_semana"] + s["gastado_hoy"] <= max(l0, 0)
    assert s["disponible_semana"] >= s["disponible_hoy"]
    assert sum(c["gasto"] for c in s["por_categoria"]) == s["gasto_periodo"]
    for key in ("saldo_libre", "cuota_hoy", "disponible_hoy", "disponible_semana"):
        assert isinstance(s[key], Decimal) and s[key] == s[key].quantize(D("0.01"))

    # Un gasto más nunca mejora nada; una devolución más nunca empeora nada.
    more = summary(budget, day, [*movements, Movement(day, extra, SPENDING, "X")], [])
    back = summary(budget, day, [*movements, Movement(day, extra, REFUND, "X")], [])
    for key in (
        "saldo_libre",
        "disponible_hoy",
        "disponible_semana",
        "maximo_apartable",
    ):
        assert more[key] <= s[key] <= back[key]
    if days > 1:
        assert more["diario_desde_manana"] <= s["diario_desde_manana"]


# ---------------------------------------------------------------- renovación y referencia (Paso 12)
def test_month_bounds():
    assert month_bounds(date(2026, 11, 25)) == (date(2026, 11, 1), date(2026, 11, 30))
    assert month_bounds(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert month_bounds(date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_renew_takes_the_current_month_with_the_last_amount():
    october = Budget(date(2026, 10, 1), date(2026, 10, 31), D("900000.00"))
    assert renew(october, WED) == Budget(
        NOV.start, NOV.end, D("900000.00"), renewed=True
    )
    # Un periodo a medida que terminó dentro del mes: la renovación empieza al día siguiente.
    custom = Budget(date(2026, 10, 15), date(2026, 11, 10), D("5.00"))
    assert renew(custom, WED).start == date(2026, 11, 11)
    assert state(budget=renew(october, WED))["periodo"]["renovado"] is True


def test_reference_proposes_spending_not_income():
    ref = reference(
        [
            spend(date(2026, 10, 3), "800000.00"),
            spend(date(2026, 10, 4), "50000.00", kind=REFUND),
            spend(date(2026, 10, 1), "3000000.00", "Ingresos", EARNING),
            spend(date(2026, 10, 2), "100000.00", "Ingresos", EARNING, in_review=True),
            spend(date(2026, 10, 5), "32000.00", kind=CASH_INVOICE),
        ]
    )
    assert ref == {"gasto": D("750000.00"), "ingresos": D("3000000.00")}
