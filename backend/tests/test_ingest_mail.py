"""Filtro, DKIM, limpieza y cifrado de correos (sin red). Muestras inventadas en tests/samples."""

import base64
import os
from email.message import EmailMessage
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from app.config import settings
from app.ingest import crypto, mail

SAMPLES = Path(__file__).parent / "samples"


def raw(name: str, *replace: tuple[bytes, bytes]) -> bytes:
    data = (SAMPLES / name).read_bytes()
    for old, new in replace:
        assert old in data, old
        data = data.replace(old, new)
    return data


def classify(data: bytes) -> mail.Decision:
    return mail.classify(mail.parse(data))


# ---------------------------------------------------------------- filtro y DKIM
def test_bank_alert_signed_by_the_bank_is_accepted():
    d = classify(raw("bancolombia_compra.eml"))
    assert (d.accepted, d.rule, d.sender_domain) == (
        True,
        "bancolombia",
        "notificacionesbancolombia.com",
    )


def test_header_d_is_accepted_like_header_i():
    d = classify(
        raw(
            "bancolombia_compra.eml",
            (
                b"header.i=@notificacionesbancolombia.com",
                b"header.d=notificacionesbancolombia.com",
            ),
        )
    )
    assert d.accepted


def test_fake_header_injected_below_gmail_is_ignored():
    msg = mail.parse(raw("bancolombia_dkim_inyectado.eml"))
    assert (
        mail.dkim_pass_domains(msg) == set()
    )  # solo cuenta el de arriba, que dice fail
    assert mail.classify(msg).reason == "dkim"


def test_dkim_pass_from_another_domain_is_rejected():
    d = classify(raw("bancolombia_dkim_otro_dominio.eml"))
    assert (d.accepted, d.reason) == (False, "dkim")


def test_results_not_added_by_gmail_are_not_trusted():
    d = classify(
        raw(
            "bancolombia_compra.eml",
            (
                b"Authentication-Results: mx.google.com;",
                b"Authentication-Results: mx.otro.example;",
            ),
        )
    )
    assert d.reason == "dkim"


def test_security_validation_is_discarded():
    d = classify(raw("bancolombia_validacion.eml"))
    assert (d.accepted, d.reason) == (False, "discarded")


def test_unknown_sender_has_no_rule():
    assert classify(raw("boletin.eml")).reason == "no_rule"


def test_invoice_with_xml_signed_by_sender_domain_is_accepted():
    d = classify(raw("factura_electronica.eml"))
    assert (d.accepted, d.rule) == (True, mail.INVOICE_RULE)


def test_invoice_signed_by_another_domain_is_rejected():
    d = classify(
        raw(
            "factura_electronica.eml",
            (
                b"@facturacion.comercio-ejemplo.example header.s",
                b"@otro.example header.s",
            ),
        )
    )
    assert d.reason == "dkim"


def test_invoice_subject_must_be_document_type_01():
    assert (
        classify(raw("factura_electronica.eml", (b";01;", b";91;"))).reason == "no_rule"
    )


# ---------------------------------------------------------------- limpieza y duplicados
def attachment_names(data: bytes) -> list[str]:
    return [p.get_filename() for p in mail.parse(data).iter_attachments()]


def test_invoice_keeps_only_the_zip():
    clean = mail.sanitize(mail.parse(raw("factura_electronica.eml")), mail.INVOICE_RULE)
    assert attachment_names(clean) == ["z0900000000001.zip"]
    assert (
        "adjuntamos su factura" in mail.parse(clean).get_body(("plain",)).get_content()
    )


def test_bank_alert_keeps_no_attachments():
    msg = mail.parse(raw("bancolombia_compra.eml"))
    msg.add_attachment(
        b"%PDF-1.4", maintype="application", subtype="pdf", filename="extracto.pdf"
    )
    clean = mail.sanitize(msg, "bancolombia")
    assert attachment_names(clean) == []
    assert (
        "MARCADOR-CUERPO-7F3A" in mail.parse(clean).get_body(("plain",)).get_content()
    )


def test_same_message_id_gives_same_hash():
    a = raw("bancolombia_compra.eml")
    b = b"X-Reenviado: 1\r\n" + a
    assert mail.message_hash(mail.parse(a), a) == mail.message_hash(mail.parse(b), b)
    no_id = EmailMessage()
    no_id.set_content("sin Message-ID")
    assert len(mail.message_hash(no_id, bytes(no_id))) == 64


def test_oversized_mail_is_refused_before_parsing():
    with pytest.raises(ValueError):
        mail.parse(b"x" * (mail.MAX_PARSED_BYTES + 1))


# ---------------------------------------------------------------- cifrado
def new_key(version: int) -> str:
    return f"{version}:{base64.b64encode(os.urandom(32)).decode()}"


@pytest.fixture
def key_v1(monkeypatch):
    key = new_key(1)
    monkeypatch.setattr(settings, "email_keys", key)
    return key


def test_encrypt_roundtrip_with_version(key_v1):
    version, blob = crypto.encrypt(b"MARCADOR", b"usuario:hash")
    assert version == 1 and b"MARCADOR" not in blob
    assert crypto.decrypt(version, blob, b"usuario:hash") == b"MARCADOR"


def test_ciphertext_is_bound_to_its_row(key_v1):
    version, blob = crypto.encrypt(b"MARCADOR", b"usuario-a:hash")
    with pytest.raises(InvalidTag):
        crypto.decrypt(version, blob, b"usuario-b:hash")


def test_key_rotation_keeps_old_mails_readable(key_v1, monkeypatch):
    old_version, old_blob = crypto.encrypt(b"viejo", b"aad")
    monkeypatch.setattr(settings, "email_keys", f"{key_v1},{new_key(2)}")
    new_version, _ = crypto.encrypt(b"nuevo", b"aad")
    assert (old_version, new_version) == (1, 2)
    assert crypto.decrypt(1, old_blob, b"aad") == b"viejo"


def test_wrong_key_length_is_refused(monkeypatch):
    monkeypatch.setattr(
        settings, "email_keys", f"1:{base64.b64encode(os.urandom(16)).decode()}"
    )
    with pytest.raises(ValueError):
        crypto.encrypt(b"x", b"aad")


# ---------------------------------------------------------------- carpetas (D8)
@pytest.mark.parametrize(
    "kind, labels, allowed",
    [
        ("bank", ["SPAM"], True),
        ("bank", ["INBOX"], True),
        ("invoice", ["INBOX"], True),
        ("invoice", ["SPAM"], False),
        ("bank", ["SENT", "INBOX"], False),
        ("invoice", ["DRAFT", "INBOX"], False),
        ("bank", ["TRASH", "SPAM"], False),
        ("bank", ["CATEGORY_UPDATES"], False),
    ],
)
def test_allowed_location(kind, labels, allowed):
    assert mail.allowed_location(kind, labels) is allowed


def test_candidate_kind():
    assert (
        mail.candidate_kind(
            "A <alertasynotificaciones@notificacionesbancolombia.com>", "x"
        )
        == "bank"
    )
    assert (
        mail.candidate_kind(
            "B <validaciondeseguridad@notificacionesbancolombia.com>", "x"
        )
        is None
    )
    assert (
        mail.candidate_kind("C <f@c.example>", "900000000;C SAS;FE-1;01;C") == "invoice"
    )
    assert mail.candidate_kind("D <o@t.example>", "Ofertas") is None
