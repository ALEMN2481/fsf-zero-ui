"""Lectura de los datos del motor con el JWT del usuario (RLS decide qué filas ve, D4).

[rest] es una función ruta → filas (main._rest ligado al usuario). amount::text: el numeric llega
como texto exacto y se convierte a Decimal, nunca a float.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import quote

from app.engine.gps import Budget, Movement, classify
from app.extract.bancolombia import COLOMBIA


def _day(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).astimezone(COLOMBIA).date()


def _bounds(budget: Budget) -> str:
    """Filtro occurred_at dentro del periodo, con los días en hora de Colombia."""
    start = datetime.combine(budget.start, time(), COLOMBIA).isoformat()
    end = datetime.combine(budget.end + timedelta(days=1), time(), COLOMBIA).isoformat()
    return f"and=(occurred_at.gte.{quote(start)},occurred_at.lt.{quote(end)})"


def budget_for(rest: Callable[[str], list[dict]], today: date) -> Budget | None:
    rows = rest(
        f"budgets?period_start=lte.{today}&period_end=gte.{today}"
        "&select=period_start,period_end,amount::text"
    )
    if not rows:
        return None
    r = rows[0]  # sin solapes: lo garantiza la restricción de la tabla
    return Budget(
        date.fromisoformat(r["period_start"]),
        date.fromisoformat(r["period_end"]),
        Decimal(r["amount"]),
    )


def load(
    rest: Callable[[str], list[dict]], today: date
) -> tuple[Budget | None, list[Movement], list[tuple[date, Decimal]]]:
    budget = budget_for(rest, today)
    if budget is None:
        return None, [], []
    own = {a["last4"] for a in rest("accounts?select=last4") if a["last4"]}
    movements = [
        Movement(
            day=_day(t["occurred_at"]),
            amount=Decimal(t["amount"]),
            kind=classify(
                t["direction"],
                t["status"],
                (t["category"] or {}).get("name"),
                t["counts_in_budget"],
                t["to_last4"],
                own,
            ),
            category=(t["category"] or {}).get("name") or "Sin categoría",
            in_review=t["status"] == "pending_review",
        )
        for t in rest(
            f"transactions?{_bounds(budget)}&select=amount::text,direction,status,"
            "occurred_at,counts_in_budget,to_last4,category:categories(name)"
        )
    ]
    pockets = [
        (_day(p["occurred_at"]), Decimal(p["amount"]))
        for p in rest(
            f"pocket_movements?{_bounds(budget)}&select=amount::text,occurred_at"
        )
    ]
    return budget, movements, pockets
