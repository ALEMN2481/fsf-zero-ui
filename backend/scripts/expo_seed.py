"""Datos de la expo (D17, Paso 15): regenera siempre los mismos datos de ejemplo en UNA cuenta del
Supabase LOCAL.

    cd backend && .venv/Scripts/python.exe -m scripts.expo_seed --email <correo de la cuenta>

Borra los datos de esa cuenta (movimientos, correos guardados, presupuestos, bolsillos, reglas
aprendidas, cuentas y conversación del Coach) y deja el mismo presupuesto, los mismos bolsillos y
los mismos movimientos de ejemplo, con fechas relativas al día en que se corre. Conserva el
perfil, la conexión de Gmail y el dispositivo registrado para los avisos. Nunca contra la nube.
"""

import sys
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse

from app import service_db
from app.config import settings
from app.engine.gps import month_bounds
from app.extract.bancolombia import COLOMBIA

BUDGET = "2000000.00"
POCKETS = [
    ("Viaje", "1000000.00", "350000.00"),
    ("Emergencias", "2000000.00", "500000.00"),
]
# (días atrás, hora, comercio, monto, medio de pago, categoría, dirección, estado)
MOVEMENTS = [
    (None, 7, "EMPRESA EMPLEADORA EJEMPLO SAS", "2500000.00", "transfer", "Ingresos", "income", "confirmed"),
    (1, 18, "SUPERMERCADO EJEMPLO SAS", "45900.00", "credit_card", "Alimentos", "expense", "confirmed"),
    (1, 8, "CAFETERIA EJEMPLO", "18000.00", "debit_card", "Alimentos", "expense", "confirmed"),
    (2, 19, "TAXI EJEMPLO", "12500.00", "debit_card", "Transporte", "expense", "confirmed"),
    (2, 12, "FERRETERIA EJEMPLO SAS", "61250.00", "credit_card", "Otros", "expense", "pending_review"),
    (3, 17, "DROGUERIA EJEMPLO", "12000.00", "credit_card", "Salud", "expense", "confirmed"),
    (4, 20, "CINE EJEMPLO", "24000.00", "credit_card", "Entretenimiento", "expense", "confirmed"),
    (5, 9, "EMPRESA DE ENERGIA EJEMPLO", "95300.00", "transfer", "Servicios", "expense", "confirmed"),
    (6, 9, "INTERNET EJEMPLO", "79900.00", "transfer", "Servicios", "expense", "confirmed"),
]  # fmt: skip
# Hijas antes que madres (claves foráneas).
OWNED = [
    "pocket_movements",
    "pockets",
    "transactions",
    "budgets",
    "inbound_emails",
    "category_rules",
    "coach_messages",
    "accounts",
]


def _rest(method: str, table: str, **kw) -> list:
    return service_db.rest(method, table, prefer="return=representation", **kw).json()


def seed(user_id: str, today: date) -> dict[str, int]:
    """Deja la cuenta con los datos de la expo. Devuelve cuántas filas creó de cada tipo."""
    for table in OWNED:
        service_db.rest("DELETE", table, params={"user_id": f"eq.{user_id}"})
    first, last = month_bounds(today)
    _rest(
        "POST",
        "budgets",
        json={
            "user_id": user_id,
            "period_start": str(first),
            "period_end": str(last),
            "amount": BUDGET,
        },
    )
    for name, target, saved in POCKETS:
        [pocket] = _rest(
            "POST",
            "pockets",
            json={"user_id": user_id, "name": name, "target_amount": target},
        )
        _rest(
            "POST",
            "pocket_movements",
            json={"user_id": user_id, "pocket_id": pocket["id"], "amount": saved},
        )
    categories = {
        c["name"]: c["id"]
        for c in _rest(
            "GET", "categories", params={"user_id": "is.null", "select": "id,name"}
        )
    }
    now = datetime.now(COLOMBIA).isoformat()
    rows = []
    for i, (
        days,
        hour,
        merchant,
        amount,
        method,
        category,
        direction,
        status,
    ) in enumerate(MOVEMENTS):
        # Dentro del mes en curso: si la expo es a comienzos de mes, se agrupan el día 1.
        day = first if days is None else max(first, today - timedelta(days=days))
        rows.append(
            {
                "user_id": user_id,
                "direction": direction,
                "amount": amount,
                "merchant": merchant,
                "occurred_at": datetime.combine(day, time(hour), COLOMBIA).isoformat(),
                "payment_method": method,
                "source": "email",
                "source_ref": f"expo:{i}",
                "status": status,
                "category_id": categories[category],
                "category_source": "direccion" if direction == "income" else "regla",
                "notified_at": now,  # los datos de ejemplo no avisan
            }
        )
    _rest("POST", "transactions", json=rows)
    return {"presupuestos": 1, "bolsillos": len(POCKETS), "movimientos": len(rows)}


def _user_id(email: str) -> str:
    key = settings.supabase_service_role_key
    users = service_db.http.get(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"per_page": 1000},
    ).json()["users"]
    found = [u["id"] for u in users if (u.get("email") or "").lower() == email.lower()]
    if not found:
        sys.exit("No hay una cuenta con ese correo en el Supabase local")
    return found[0]


def main(argv: list[str]) -> None:
    if urlparse(settings.supabase_url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("Solo contra el Supabase local (D17)")
    if len(argv) != 2 or argv[0] != "--email":
        sys.exit("Uso: python -m scripts.expo_seed --email <correo de la cuenta>")
    counts = seed(_user_id(argv[1]), datetime.now(COLOMBIA).date())
    print("datos de la expo listos:", counts)


if __name__ == "__main__":
    main(sys.argv[1:])
