"""Lectura de los datos del motor con el JWT del usuario (RLS decide qué filas ve, D4).

[rest] es una función ruta → filas (main._rest ligado al usuario). amount::text: el numeric llega
como texto exacto y se convierte a Decimal, nunca a float.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import quote

from app.engine.gps import Budget, Movement, classify, month_bounds, renew
from app.extract.bancolombia import COLOMBIA

Rest = Callable[[str], list[dict]]


def _day(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).astimezone(COLOMBIA).date()


def _bounds(first: date, last: date) -> str:
    """Filtro occurred_at entre dos días (incluidos), en hora de Colombia."""
    start = datetime.combine(first, time(), COLOMBIA).isoformat()
    end = datetime.combine(last + timedelta(days=1), time(), COLOMBIA).isoformat()
    return f"and=(occurred_at.gte.{quote(start)},occurred_at.lt.{quote(end)})"


def _budget(r: dict) -> Budget:
    return Budget(
        date.fromisoformat(r["period_start"]),
        date.fromisoformat(r["period_end"]),
        Decimal(r["amount"]),
    )


def budget_for(rest: Rest, today: date) -> Budget | None:
    fields = "&select=period_start,period_end,amount::text"
    rows = rest(f"budgets?period_start=lte.{today}&period_end=gte.{today}{fields}")
    if rows:
        return _budget(rows[0])  # sin solapes: lo garantiza la restricción de la tabla
    # Sin periodo que contenga hoy: se renueva el último (anterior a hoy) para el mes en curso.
    rows = rest(f"budgets?period_end=lt.{today}&order=period_end.desc&limit=1{fields}")
    return renew(_budget(rows[0]), today) if rows else None


def own_accounts(rest: Rest) -> set[str]:
    return {a["last4"] for a in rest("accounts?select=last4") if a["last4"]}


def kind(t: dict, own: set[str]) -> str:
    return classify(
        t["direction"],
        t["status"],
        (t["category"] or {}).get("name"),
        t["counts_in_budget"],
        t["to_last4"],
        own,
    )


def movements(
    rest: Rest, first: date, last: date, own: set[str] | None = None
) -> list[Movement]:
    """Movimientos entre dos días, sin los descartados ('No es un gasto mío').

    [own]: últimos 4 dígitos de las cuentas propias, si ya se leyeron.
    """
    if own is None:
        own = own_accounts(rest)
    return [
        Movement(
            day=_day(t["occurred_at"]),
            amount=Decimal(t["amount"]),
            kind=kind(t, own),
            category=(t["category"] or {}).get("name") or "Sin categoría",
            in_review=t["status"] == "pending_review",
            method=t.get("payment_method"),
        )
        for t in rest(
            f"transactions?{_bounds(first, last)}&status=neq.dismissed"
            "&select=amount::text,direction,status,occurred_at,counts_in_budget,"
            "to_last4,payment_method,category:categories(name)"
        )
    ]


def previous_month(rest: Rest, today: date) -> list[Movement]:
    first, _ = month_bounds(today)
    return movements(rest, *month_bounds(first - timedelta(days=1)))


def load(
    rest: Rest, today: date, own: set[str] | None = None
) -> tuple[Budget | None, list[Movement], list[tuple[date, Decimal]]]:
    budget = budget_for(rest, today)
    if budget is None:
        return None, [], []
    # Bolsillos y movimientos no dependen entre sí: en paralelo (RQN 04).
    with ThreadPoolExecutor(2) as pool:
        pocket_rows = pool.submit(
            rest,
            f"pocket_movements?{_bounds(budget.start, budget.end)}"
            "&select=amount::text,occurred_at",
        )
        moves = pool.submit(movements, rest, budget.start, budget.end, own)
        pockets = [
            (_day(p["occurred_at"]), Decimal(p["amount"])) for p in pocket_rows.result()
        ]
        return budget, moves.result(), pockets
