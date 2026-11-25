"""Integración contra Supabase LOCAL: guardado cifrado, duplicados, RLS y logs sin secretos."""

import base64
import logging
import os
from pathlib import Path

import httpx
import pytest
from local_supabase import ANON, SERVICE, URL, bearer, requires_local

from app.config import settings
from app.ingest import crypto, mail
from app.ingest.store import ingest

pytestmark = requires_local

SAMPLES = Path(__file__).parent / "samples"
BODY_MARKER = "MARCADOR-CUERPO-7F3A"


@pytest.fixture
def env(users, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE)
    monkeypatch.setattr(
        settings, "email_keys", f"1:{base64.b64encode(os.urandom(32)).decode()}"
    )
    return users


def service_rows(user_id: str) -> list[dict]:
    r = httpx.get(
        f"{URL}/rest/v1/inbound_emails",
        params={"user_id": f"eq.{user_id}", "select": "*"},
        headers={"apikey": SERVICE, **bearer(SERVICE)},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_stores_encrypted_once_and_logs_no_secrets(env, caplog):
    caplog.set_level(logging.DEBUG)  # todos los loggers, incluidos httpx/httpcore
    a = env["a"]
    alert = (SAMPLES / "bancolombia_compra.eml").read_bytes()

    assert ingest(a["id"], alert) == "stored"
    assert ingest(a["id"], alert) == "duplicate"
    assert ingest(a["id"], (SAMPLES / "boletin.eml").read_bytes()) == "no_rule"
    assert (
        ingest(a["id"], (SAMPLES / "bancolombia_dkim_inyectado.eml").read_bytes())
        == "dkim"
    )

    rows = service_rows(a["id"])
    assert len(rows) == 1
    row = rows[0]
    assert (row["rule"], row["status"], row["key_version"]) == (
        "bancolombia",
        "pending_extraction",
        1,
    )
    blob = bytes.fromhex(row["raw_encrypted"].removeprefix("\\x"))
    assert BODY_MARKER.encode() not in blob  # en la BD solo hay texto cifrado
    plain = crypto.decrypt(
        row["key_version"], blob, f"{a['id']}:{row['message_hash']}".encode()
    )
    assert BODY_MARKER in mail.parse(plain).get_body(("plain",)).get_content()

    logs = caplog.text
    assert "correo guardado" in logs and "correo duplicado" in logs
    forbidden = [
        BODY_MARKER,
        "Alertas y Notificaciones",  # asunto
        "alertasynotificaciones@",  # dirección completa
        "usuario.ejemplo@",
        SERVICE,
        settings.email_keys.partition(":")[2],
        a["token"],
    ]
    for secret in forbidden:
        assert secret not in logs, f"secreto en logs: {secret[:12]}…"


def test_user_reads_only_own_metadata(env):
    a, b = env["a"], env["b"]
    assert (
        ingest(a["id"], (SAMPLES / "factura_electronica.eml").read_bytes()) == "stored"
    )

    def get(token, select):
        return httpx.get(
            f"{URL}/rest/v1/inbound_emails",
            params={"select": select},
            headers={"apikey": ANON, **bearer(token)},
            timeout=10,
        )

    mine = get(a["token"], "id,rule,status,sender_domain")
    assert mine.status_code == 200
    assert [(x["rule"], x["status"]) for x in mine.json()] == [
        (mail.INVOICE_RULE, "pending_extraction")
    ]
    assert get(a["token"], "raw_encrypted").status_code in (
        401,
        403,
    )  # el contenido nunca se expone
    assert get(b["token"], "id").json() == []  # B no ve los correos de A
