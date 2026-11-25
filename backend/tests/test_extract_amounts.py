from decimal import Decimal

import pytest

from app.extract.amounts import parse_cop


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$1.234.567,89", "1234567.89"),
        ("COP 50.000", "50000.00"),
        ("COP50.000,00", "50000.00"),
        ("$50,000.00", "50000.00"),
        ("$ 1.234", "1234.00"),  # 3 dígitos tras el punto: miles, no decimales
        ("1,234", "1234.00"),
        ("1,5", "1.50"),
        ("$1.50", "1.50"),
        ("12345", "12345.00"),
        ("$\xa0120.000", "120000.00"),  # espacio duro de los correos HTML
        ("120.000 COP", "120000.00"),
        ("$999.999.999.999,99", "999999999999.99"),
        ("0,01", "0.01"),
    ],
)
def test_parses_colombian_amounts(text, expected):
    amount = parse_cop(text)
    assert isinstance(amount, Decimal) and amount == Decimal(expected)
    assert amount.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "text",
    [
        "",
        "$",
        "abc",
        "0",
        "$0,00",
        "-5.000",
        "1.2345",  # grupo de 4 dígitos
        "1.23.456",  # grupo de 2 dígitos
        "1.234,567",  # mezcla sin decimal válido
        "1,234,56",  # el separador decimal no puede ser el de miles
        "$1.000.000.000.000",  # excede numeric(14, 2)
        "1e5",
    ],
)
def test_rejects_invalid_amounts(text):
    with pytest.raises(ValueError):
        parse_cop(text)
