"""Motor financiero GPS (Paso 11, D12): funciones puras con Decimal, sin BD ni reloj.

Fórmulas (documentadas en docs/CONTEXT.md §Motor financiero):
    L₀ = P − Gasto(ini..ayer) − Ap          Gh = Gasto(hoy)          L = L₀ − Gh
    n  = fin − hoy + 1                       cuotas = reparto(L₀, n)
    disponible_hoy    = cuotas[0] − Gh
    disponible_semana = Σ cuotas[0:k] − Gh,  k = min(domingo, fin) − hoy + 1
    diario_desde_mañana = reparto(L, n − 1)[0]          diario_plan = reparto(L₀ − cuotas[0], n − 1)[0]
Gasto = gastos (confirmados y en revisión) − devoluciones confirmadas. No entran: los ingresos
(categoría Ingresos), las facturas en efectivo (counts_in_budget = false) ni las transferencias a
una cuenta propia registrada.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
INCOME = "Ingresos"

# Tipos de movimiento para el motor (classify).
SPENDING = "gasto"
REFUND = "devolucion"
REFUND_IN_REVIEW = "devolucion_en_revision"  # no cuenta hasta confirmarse
EARNING = "ingreso"
CASH_INVOICE = "efectivo_factura"  # solo para el detalle por categoría
OWN_TRANSFER = "entre_cuentas"  # no es gasto


@dataclass(frozen=True)
class Budget:
    start: date
    end: date  # incluido
    amount: Decimal
    renewed: bool = False  # mes en curso con el monto del último presupuesto (Paso 12)


@dataclass(frozen=True)
class Movement:
    day: date  # en hora de Colombia
    amount: Decimal  # siempre > 0; el signo lo da kind
    kind: str
    category: str
    in_review: bool = False


def classify(
    direction: str,
    status: str,
    category: str | None,
    counts_in_budget: bool,
    to_last4: str | None,
    own_last4: set[str],
) -> str:
    if direction == "income":
        if category in (INCOME, None):
            return EARNING
        # Ingreso con otra categoría: devolución (o el usuario lo corrigió como tal).
        return REFUND if status == "confirmed" else REFUND_IN_REVIEW
    if to_last4 and to_last4 in own_last4:
        return OWN_TRANSFER
    return SPENDING if counts_in_budget else CASH_INVOICE


def split(total: Decimal, days: int) -> list[Decimal]:
    """Reparte [total] en [days] cuotas: pesos enteros iguales; lo que sobra (pesos y centavos)
    va al último día. Σ cuotas = total exacto; con total ≤ 0, todas son 0."""
    if days < 1:
        raise ValueError("days < 1")
    if total <= 0:
        return [ZERO] * days
    base = (total.to_integral_value(ROUND_FLOOR) // days).quantize(CENT)
    return [base] * (days - 1) + [(total - base * (days - 1)).quantize(CENT)]


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    following = (start + timedelta(days=32)).replace(day=1)
    return start, following - timedelta(days=1)


def renew(last: Budget, today: date) -> Budget:
    """Presupuesto del mes en curso con el monto del último: se renueva solo, sin escribirlo.

    Empieza tras el último periodo si este terminó dentro del mes en curso, para no solaparlos.
    """
    start, end = month_bounds(today)
    return Budget(
        max(start, last.end + timedelta(days=1)), end, last.amount, renewed=True
    )


def reference(movements: list[Movement]) -> dict:
    """Referencia para proponer el presupuesto: el gasto (como en Gasto) y los ingresos
    confirmados de un periodo. Se propone el gasto, nunca el 100 % de los ingresos."""
    return {
        "gasto": _net(movements),
        "ingresos": sum(
            (m.amount for m in movements if m.kind == EARNING and not m.in_review), ZERO
        ),
    }


def progress(balance: Decimal, target: Decimal | None) -> int | None:
    """Avance de un bolsillo hacia su meta, en % entero redondeado hacia abajo (sin tope: si se
    pasa de la meta, pasa de 100). Sin meta, None."""
    if target is None or target <= 0:
        return None
    return int(max(balance, ZERO) * 100 // target)


def _net(movements) -> Decimal:
    total = ZERO
    for m in movements:
        if m.kind == SPENDING:
            total += m.amount
        elif m.kind == REFUND:
            total -= m.amount
    return total


def summary(
    budget: Budget | None,
    today: date,
    movements: list[Movement],
    pocket_moves: list[tuple[date, Decimal]],
) -> dict:
    """Estado del periodo que contiene [today]. Montos en Decimal con 2 decimales."""
    if budget is None or not budget.start <= today <= budget.end:
        return {"estado": "sin_presupuesto", "hoy": today}
    period = [m for m in movements if budget.start <= m.day <= budget.end]
    # Lo fechado después de hoy (dentro del periodo) se cuenta como de hoy: más vale restarlo ya.
    spent_before = _net(m for m in period if m.day < today)
    spent_today = _net(m for m in period if m.day >= today)
    saved = sum((a for d, a in pocket_moves if budget.start <= d <= budget.end), ZERO)

    l0 = budget.amount - spent_before - saved
    free = l0 - spent_today
    days = (budget.end - today).days + 1
    shares = split(l0, days)
    quota = shares[0]
    sunday = today + timedelta(days=6 - today.weekday())
    week_days = (min(sunday, budget.end) - today).days + 1

    categories: dict[str, dict] = defaultdict(
        lambda: {"gasto": ZERO, "efectivo_factura": ZERO}
    )
    for m in period:
        if m.kind in (SPENDING, REFUND):
            categories[m.category]["gasto"] += (
                m.amount if m.kind == SPENDING else -m.amount
            )
        elif m.kind == CASH_INVOICE:
            categories[m.category]["efectivo_factura"] += m.amount

    return {
        "estado": "ok",
        "hoy": today,
        "periodo": {
            "inicio": budget.start,
            "fin": budget.end,
            "presupuesto": budget.amount,
            "renovado": budget.renewed,
        },
        "dias_restantes": days,
        "saldo_libre": free,
        "gasto_periodo": spent_before + spent_today,
        "apartado_periodo": saved,
        "ingresos_periodo": sum((m.amount for m in period if m.kind == EARNING), ZERO),
        "en_revision": sum(
            (m.amount for m in period if m.kind == SPENDING and m.in_review), ZERO
        ),
        "cuota_hoy": quota,
        "gastado_hoy": spent_today,
        "disponible_hoy": quota - spent_today,
        "exceso": max(spent_today - quota, ZERO),
        "diario_plan": split(l0 - quota, days - 1)[0] if days > 1 else None,
        "diario_desde_manana": split(free, days - 1)[0] if days > 1 else None,
        "disponible_semana": sum(shares[:week_days], ZERO) - spent_today,
        "maximo_apartable": max(free, ZERO),
        "por_categoria": [
            {"categoria": name, **values} for name, values in sorted(categories.items())
        ],
    }
