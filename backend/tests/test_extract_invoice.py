"""Paso 09A: factura electrónica DIAN leída de forma segura y determinista (muestras inventadas)."""

import io
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.extract import invoice as inv
from app.extract.invoice import check_invoice, normalize_email

SAMPLE = (
    Path(__file__).parent / "samples" / "dian" / "attached_document.xml"
).read_text(encoding="utf-8")
CUFE = "c0ffee" + "0" * 89 + "1"
USER = "comprador.prueba@gmail.com"


def zip_of(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def invoice_zip(xml: str = SAMPLE) -> bytes:
    return zip_of(
        {"ad09000000012026.xml": xml, "ad09000000012026.pdf": b"%PDF-1.4 ficticio"}
    )


def check(xml: str = SAMPLE, user: str = USER):
    return check_invoice(invoice_zip(xml), user)


# ---------------------------------------------------------------- lectura
def test_valid_invoice_is_confirmed_with_all_fields():
    r = check()
    assert (r.status, r.reason) == ("confirmed", None)
    i = r.invoice
    assert i.number == "FEPR-1001"
    assert i.cufe == CUFE
    assert i.issued_at == datetime(
        2026, 11, 20, 13, 45, 10, tzinfo=timezone(timedelta(hours=-5))
    )
    assert i.supplier_name == "Tienda Ficticia de Prueba S.A.S."
    assert i.supplier_nit == "900000001"
    assert i.total == Decimal("50000.00") and isinstance(i.total, Decimal)
    assert i.currency == "COP"
    assert i.payment_method == "cash"


def test_issue_time_without_zone_is_colombian_time():
    r = check(SAMPLE.replace("13:45:10-05:00", "13:45:10"))
    assert r.invoice.issued_at.utcoffset() == timedelta(hours=-5)


@pytest.mark.parametrize(
    "codes, expected",
    [
        (["48"], "credit_card"),
        (["49"], "debit_card"),
        (["47"], "transfer"),
        (["ZZZ"], "other"),
        (["10", "48"], "other"),
    ],
)
def test_payment_means(codes, expected):
    means = "".join(
        f"<cac:PaymentMeans><cbc:ID>1</cbc:ID><cbc:PaymentMeansCode>{c}</cbc:PaymentMeansCode>"
        "</cac:PaymentMeans>"
        for c in codes
    )
    xml = SAMPLE.replace(
        "<cac:PaymentMeans>\n    <cbc:ID>1</cbc:ID>\n    <cbc:PaymentMeansCode>10</cbc:PaymentMeansCode>\n"
        "  </cac:PaymentMeans>",
        means,
    )
    assert xml != SAMPLE
    assert check(xml).invoice.payment_method == expected


# ---------------------------------------------------------------- comprador (correo = Gmail conectado)
@pytest.mark.parametrize(
    "user",
    [
        "comprador.prueba@gmail.com",
        "COMPRADORPRUEBA@gmail.com",
        "comprador.prueba+fsf@googlemail.com",
    ],
)
def test_buyer_matches_same_gmail_mailbox(user):
    assert check(user=user).status == "confirmed"


def test_buyer_with_several_addresses_matches_any():
    xml = SAMPLE.replace(
        "Comprador.Prueba@gmail.com",
        "contabilidad@example.com; comprador.prueba@gmail.com",
    )
    assert check(xml).status == "confirmed"


def test_invoice_for_someone_else_goes_to_review():
    r = check(user="otra.persona@gmail.com")
    assert (r.status, r.reason) == ("pending_review", "comprador_distinto")
    assert r.invoice is not None  # se conserva para la revisión


def test_invoice_without_buyer_email_goes_to_review():
    xml = SAMPLE.replace(
        "<cbc:ElectronicMail>Comprador.Prueba@gmail.com</cbc:ElectronicMail>", ""
    )
    assert check(xml).reason == "comprador_distinto"


def test_email_normalization_only_folds_gmail():
    assert normalize_email(" A.B+x@GMAIL.com ") == "ab@gmail.com"
    assert normalize_email("a.b+x@empresa.co") == "a.b+x@empresa.co"


# ---------------------------------------------------------------- comprobación estructural DIAN
def test_rejected_by_dian_goes_to_review():
    r = check(
        SAMPLE.replace(
            "<cbc:ResponseCode>02</cbc:ResponseCode>",
            "<cbc:ResponseCode>04</cbc:ResponseCode>",
        )
    )
    assert (r.status, r.reason) == ("pending_review", "dian_no_validada")


def test_response_for_another_cufe_goes_to_review():
    other = "d" * 96
    # Solo el CUFE del ApplicationResponse (el último de los tres).
    head, _, tail = SAMPLE.rpartition(CUFE)
    r = check(head + other + tail)
    assert (r.status, r.reason) == ("pending_review", "dian_no_validada")


def test_malformed_cufe_goes_to_review():
    assert check(SAMPLE.replace(CUFE, "abc123")).reason == "cufe_formato"


def test_foreign_currency_goes_to_review():
    xml = SAMPLE.replace(
        '<cbc:PayableAmount currencyID="COP">', '<cbc:PayableAmount currencyID="USD">'
    )
    assert check(xml).reason == "moneda"


@pytest.mark.parametrize(
    "old, new, reason",
    [
        ("<cbc:IssueTime>13:45:10-05:00</cbc:IssueTime>", "", "xml_falta:IssueTime"),
        (
            "50000.00</cbc:PayableAmount>",
            "cincuenta</cbc:PayableAmount>",
            "xml_valor_invalido",
        ),
        (
            "50000.00</cbc:PayableAmount>",
            "0.00</cbc:PayableAmount>",
            "xml_valor_invalido",
        ),
        (
            "50000.00</cbc:PayableAmount>",
            "NaN</cbc:PayableAmount>",
            "xml_valor_invalido",
        ),
        (
            "<cbc:DocumentType>ApplicationResponse</cbc:DocumentType>\n      <cac:Attachment>",
            "<cbc:DocumentType>ApplicationResponse</cbc:DocumentType>\n      <cac:Attachmentx>",
            "xml_invalido",
        ),
    ],
)
def test_incomplete_or_broken_xml_goes_to_review(old, new, reason):
    assert old in SAMPLE
    r = check(SAMPLE.replace(old, new, 1))
    assert (r.status, r.reason, r.invoice) == ("pending_review", reason, None)


def test_bare_invoice_without_dian_container_goes_to_review():
    bare = SAMPLE.split("<![CDATA[", 1)[1].split("]]>", 1)[0]
    assert check(bare).reason == "xml_tipo_inesperado"


# ---------------------------------------------------------------- XML seguro (defusedxml)
XXE = """<?xml version="1.0"?>
<!DOCTYPE AttachedDocument [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2">&x;</AttachedDocument>"""
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
<l>&b;</l>"""


@pytest.mark.parametrize("xml", [XXE, BILLION_LAUGHS])
def test_xml_with_dtd_or_entities_is_refused(xml):
    assert check(xml).reason == "xml_inseguro"


def test_entities_inside_the_embedded_invoice_are_refused_too():
    xml = SAMPLE.replace(
        '<![CDATA[<?xml version="1.0" encoding="UTF-8"?>\n<Invoice',
        '<![CDATA[<?xml version="1.0"?>\n<!DOCTYPE Invoice [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n<Invoice',
        1,
    )
    assert xml != SAMPLE
    assert check(xml).reason == "xml_inseguro"


# ---------------------------------------------------------------- .zip seguro
@pytest.mark.parametrize(
    "files, reason",
    [
        (
            {f"f{i}.txt": "x" for i in range(inv.MAX_FILES + 1)},
            "zip_demasiados_archivos",
        ),
        ({"../../fuera.xml": SAMPLE}, "zip_ruta_peligrosa"),
        ({"/abs.xml": SAMPLE}, "zip_ruta_peligrosa"),
        ({"C:/abs.xml": SAMPLE}, "zip_ruta_peligrosa"),
        ({"otro.zip": b"PK", "f.xml": SAMPLE}, "zip_anidado"),
        ({"solo.pdf": b"%PDF"}, "zip_sin_un_xml"),
        ({"a.xml": SAMPLE, "b.xml": SAMPLE}, "zip_sin_un_xml"),
        ({"grande.xml": " " * (inv.MAX_UNCOMPRESSED + 10)}, "zip_demasiado_grande"),
        ({"bomba.xml": "a" * (1024 * 1024)}, "zip_compresion_sospechosa"),
    ],
)
def test_unsafe_archives_are_refused(files, reason):
    r = check_invoice(zip_of(files), USER)
    assert (r.status, r.reason) == ("pending_review", reason)


def test_not_a_zip_is_refused():
    assert check_invoice(b"esto no es un zip", USER).reason == "zip_invalido"


def test_encrypted_entry_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("f.xml", SAMPLE)
    data = bytearray(buf.getvalue())
    # Marca de cifrado (bit 0 de los flags) en la cabecera local y en el directorio central.
    for sig, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = data.find(sig)
        data[pos + offset] |= 0x1
    assert check_invoice(bytes(data), USER).reason == "zip_cifrado"
