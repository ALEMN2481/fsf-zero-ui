"""Alertas de Bancolombia → movimiento, con plantillas fijas (Paso 09B, sin LLM).

Las plantillas salen de alertas simuladas por el supervisor (formatos aproximados, sin confirmar
contra correos reales). Por eso son estrictas: cada una está anclada a sus palabras fijas y tiene
que encajar exactamente una; si no encaja ninguna, encajan varias o un dato no se valida
(monto, fecha, comercio), la alerta va a 'pending_review'. Nunca se adivina un dato.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extract.amounts import parse_cop

COLOMBIA = timezone(timedelta(hours=-5))
# Se compara sin tildes ni mayúsculas, pero los datos se toman del texto original (mismas posiciones).
_FOLD = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")

_AMOUNT = r"\$\s?(?P<amount>\d(?:[\d.,]*\d)?)"
_CARD = r"tu (?P<card>T\.Deb|T\.Cred) \*(?P<last4>\d{4})"
_ACCOUNT = r"tu cuenta \*(?P<last4>\d{4})"
_WHEN = r"el (?P<date>\d{2}/\d{2}/\d{4}) a las (?P<time>\d{2}:\d{2})\."
_MERCHANT = r"(?P<merchant>[^,]{1,80}?)"
_NEW = r"Bancolombia: "


@dataclass(frozen=True)
class Template:
    name: str
    pattern: re.Pattern
    direction: str | None  # None → sin movimiento
    method: str | None = None  # None → según la tarjeta (T.Deb / T.Cred)


def _t(name, regex, direction, method=None) -> Template:
    return Template(name, re.compile(regex, re.IGNORECASE), direction, method)


TEMPLATES = (
    _t(
        "compra",
        _NEW + rf"Compraste {_AMOUNT} en {_MERCHANT} con {_CARD}, {_WHEN}",
        "expense",
    ),
    _t(
        "compra_antigua",
        rf"Bancolombia le informa Compra por {_AMOUNT} en {_MERCHANT} (?P<time>\d{{2}}:\d{{2}})\. "
        r"(?P<date>\d{2}/\d{2}/\d{4}) (?P<card>T\.Deb|T\.Cred) \*(?P<last4>\d{4})\.",
        "expense",
    ),
    # Retiro y avance: gasto (decisión del supervisor, 2026-11-25).
    _t(
        "retiro",
        _NEW + rf"Retiraste {_AMOUNT} en {_MERCHANT} con {_CARD}, {_WHEN}",
        "expense",
    ),
    _t(
        "avance",
        _NEW + rf"Hiciste un avance por {_AMOUNT} con {_CARD} en {_MERCHANT}, {_WHEN}",
        "expense",
    ),
    _t(
        "transferencia_enviada",
        _NEW
        + rf"Transferiste {_AMOUNT} desde {_ACCOUNT} a la cuenta \*\d{{4}} {_WHEN}",
        "expense",
        "transfer",
    ),
    _t(
        "nomina",
        _NEW
        + rf"Recibiste un pago de nomina por {_AMOUNT} de {_MERCHANT} en {_ACCOUNT}, {_WHEN}",
        "income",
        "transfer",
    ),
    _t(
        "transferencia_recibida",
        _NEW
        + rf"Recibiste una transferencia por {_AMOUNT} de {_MERCHANT} en {_ACCOUNT}, {_WHEN}",
        "income",
        "transfer",
    ),
    _t(
        "pse",
        _NEW + rf"Pagaste {_AMOUNT} a {_MERCHANT} por PSE desde {_ACCOUNT}, {_WHEN}",
        "expense",
        "transfer",
    ),
    _t(
        "factura",
        _NEW
        + rf"Pagaste la factura de {_MERCHANT} por {_AMOUNT} desde {_ACCOUNT}, {_WHEN}",
        "expense",
        "transfer",
    ),
    _t(
        "qr",
        _NEW
        + rf"Pagaste {_AMOUNT} con codigo QR a {_MERCHANT} desde {_ACCOUNT}, {_WHEN}",
        "expense",
        "transfer",
    ),
    _t(
        "devolucion",
        _NEW
        + rf"Recibiste una devolucion por {_AMOUNT} de {_MERCHANT} en {_CARD}, {_WHEN}",
        "income",
    ),
    # Sin movimiento: el pago de la propia tarjeta (sus compras ya se cuentan una a una;
    # decisión del supervisor) y la compra rechazada.
    _t(
        "pago_tarjeta",
        _NEW + rf"Pagaste {_AMOUNT} a tu T\.Cred \*\d{{4}} desde {_ACCOUNT}, {_WHEN}",
        None,
    ),
    _t(
        "compra_rechazada",
        _NEW
        + rf"Tu compra por {_AMOUNT} en {_MERCHANT} con {_CARD} no fue exitosa, {_WHEN}",
        None,
    ),
)
_CARD_METHOD = {"t.deb": "debit_card", "t.cred": "credit_card"}


@dataclass(frozen=True)
class Alert:
    status: str  # confirmed | pending_review | no_movement
    reason: str | None = None
    template: str | None = None
    direction: str | None = None
    amount: Decimal | None = None
    merchant: str | None = None
    occurred_at: datetime | None = None
    payment_method: str | None = None
    last4: str | None = None


def parse_alert(text: str) -> Alert:
    original = " ".join(text.split())
    folded = original.translate(_FOLD)
    # Todas las coincidencias, también repetidas: un correo con dos alertas no se lee a medias.
    found = [(t, m) for t in TEMPLATES for m in t.pattern.finditer(folded)]
    if not found:
        return Alert("pending_review", "sin_plantilla")
    if len(found) > 1:
        return Alert("pending_review", "varias_plantillas")
    template, m = found[0]
    if template.direction is None:
        return Alert("no_movement", template=template.name)

    def group(name: str) -> str | None:
        return original[m.start(name) : m.end(name)] if name in m.groupdict() else None

    try:
        amount = parse_cop(group("amount"))
    except ValueError:
        return Alert("pending_review", "monto", template.name)
    try:
        when = datetime.strptime(f"{group('date')} {group('time')}", "%d/%m/%Y %H:%M")
    except ValueError:
        return Alert("pending_review", "fecha", template.name)
    merchant = group("merchant")
    if merchant is not None:
        merchant = merchant.strip()
        if not merchant:
            return Alert("pending_review", "comercio", template.name)
    return Alert(
        "confirmed",
        template=template.name,
        direction=template.direction,
        amount=amount,
        merchant=merchant,
        occurred_at=when.replace(tzinfo=COLOMBIA),
        payment_method=template.method or _CARD_METHOD[group("card").casefold()],
        last4=group("last4"),
    )
