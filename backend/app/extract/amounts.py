"""Montos colombianos a Decimal. Nunca float (RQN 03)."""

import re
from decimal import Decimal

MAX_AMOUNT = Decimal("999999999999.99")  # transactions.amount es numeric(14, 2)
_NUMBER = re.compile(r"\d[\d.,]*")
_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def parse_cop(text: str) -> Decimal:
    """'$1.234.567,89', 'COP 50.000', '$50,000.00', '1,5' → Decimal con 2 decimales.

    El último separador es decimal si le siguen 1 o 2 dígitos; si no, todos son de miles
    (en COP no hay 3 decimales). Lanza ValueError si no es un monto positivo válido.
    """
    s = re.sub(
        r"(?i)^\s*(cop|col)?\s*\$?\s*|\s*(cop)?\s*$", "", text.replace("\xa0", " ")
    )
    if not _NUMBER.fullmatch(s):
        raise ValueError(f"monto no reconocido: {text!r}")
    last = max(s.rfind("."), s.rfind(","))
    if last != -1 and 1 <= len(s) - last - 1 <= 2:
        integer, decimals = s[:last], s[last + 1 :]
    else:
        integer, decimals = s, ""
    if any(c in integer for c in ".,"):
        # Los separadores de miles: uno solo y en grupos de 3 ('1.234,567' o '1.23.456' no valen).
        if not _THOUSANDS.fullmatch(integer) or ("." in integer and "," in integer):
            raise ValueError(f"monto no reconocido: {text!r}")
        if decimals and s[last] in integer:
            raise ValueError(f"monto ambiguo: {text!r}")
        integer = re.sub(r"[.,]", "", integer)
    amount = Decimal(f"{integer}.{decimals or '0'}").quantize(Decimal("0.01"))
    if not 0 < amount <= MAX_AMOUNT:
        raise ValueError(f"monto fuera de rango: {text!r}")
    return amount
