"""Paso 09B: variantes INVENTADAS por el desarrollador (no del supervisor).

Lo que no encaja exactamente con una plantilla va a pending_review: nunca a un dato equivocado.
"""

from decimal import Decimal

import pytest

from app.extract.bancolombia import parse_alert

BASE = (
    "Bancolombia: Compraste $23.500,00 en PANADERIA EJEMPLO con tu T.Deb *0000, "
    "el 23/11/2026 a las 07:45. Si tienes dudas, encuentranos aqui: 000 000 0000."
)


def test_base_alert_is_confirmed():
    a = parse_alert(BASE)
    assert (a.status, a.amount, a.merchant) == (
        "confirmed",
        Decimal("23500.00"),
        "PANADERIA EJEMPLO",
    )


def test_tolerates_line_breaks_spacing_case_and_accents():
    text = "  bancolombia:   COMPRASTE $23.500,00\n en Panadería Ejemplo con tu T.DEB *0000,\r\n el 23/11/2026 a las 07:45."
    a = parse_alert(text.replace("\n", "\n").replace("\r", "\r"))
    assert (a.status, a.merchant, a.payment_method) == (
        "confirmed",
        "Panadería Ejemplo",
        "debit_card",
    )


def test_html_body_text_is_parsed():
    from email.message import EmailMessage

    from app.extract.pipeline import body_text

    html_only = EmailMessage()
    html_only.set_content(f"<p>{BASE.replace('$', '&#36;')}</p>", subtype="html")
    assert parse_alert(body_text(html_only)).status == "confirmed"


@pytest.mark.parametrize(
    "variant, reason",
    [
        (BASE.replace("$23.500,00", "USD23,50"), "sin_plantilla"),  # otra moneda
        (BASE.replace("$23.500,00", "US$23,50"), "sin_plantilla"),
        (
            BASE.replace("$23.500,00", "$23.5000,00"),
            "monto",
        ),  # grupo de miles mal formado
        (BASE.replace("23/11/2026", "31/02/2026"), "fecha"),  # fecha imposible
        (BASE.replace("07:45", "25:45"), "fecha"),
        (
            BASE.replace("PANADERIA EJEMPLO", "PANADERIA, EJEMPLO"),
            "sin_plantilla",
        ),  # coma en el comercio
        (
            BASE.replace("T.Deb", "Tarjeta Debito"),
            "sin_plantilla",
        ),  # otra forma de nombrar la tarjeta
        (BASE.replace("*0000", "*00000"), "sin_plantilla"),
        (BASE.replace("Compraste", "Compraste y te devolvimos"), "sin_plantilla"),
        (
            BASE.replace("en PANADERIA EJEMPLO", "en " + "X" * 81),
            "sin_plantilla",
        ),  # comercio demasiado largo
        (BASE + " " + BASE, "varias_plantillas"),  # dos alertas en un correo
        ("Bancolombia: Tu clave dinamica es 000000.", "sin_plantilla"),
        ("", "sin_plantilla"),
    ],
)
def test_anything_that_does_not_fit_goes_to_review(variant, reason):
    a = parse_alert(variant)
    assert (a.status, a.reason, a.amount) == ("pending_review", reason, None)
