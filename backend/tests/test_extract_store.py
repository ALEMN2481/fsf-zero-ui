"""Paso 09B, integración contra Supabase LOCAL: correo → transactions y doble conteo en los dos órdenes."""

import base64
import json
import logging
import os
import re
import uuid
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest
from local_supabase import SERVICE, URL, bearer, requires_local

from app.config import settings
from app.ingest.store import ingest

pytestmark = requires_local

SUP = Path(__file__).parent / "samples" / "supervisor"
GMAIL = "cliente.ejemplo@gmail.com"  # comprador de las facturas del supervisor
ALERTS = dict(
    re.findall(
        r"\[(A\d+)\]\nAsunto:[^\n]*\n(.*?)(?=\n-----|\Z)",
        (SUP / "alertas.txt").read_text(encoding="utf-8"),
        re.DOTALL,
    )
)
H = {"apikey": SERVICE, **bearer(SERVICE)}


def svc(method, table, headers=None, **kw):
    r = httpx.request(
        method,
        f"{URL}/rest/v1/{table}",
        headers={**H, **(headers or {})},
        timeout=30,
        **kw,
    )
    assert r.status_code < 300, r.text
    return r.json() if r.content else None


@pytest.fixture
def env(users, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE)
    monkeypatch.setattr(
        settings, "email_keys", f"1:{base64.b64encode(os.urandom(32)).decode()}"
    )
    a = users["a"]
    svc(
        "POST",
        "gmail_connections",
        json={
            "user_id": a["id"],
            "gmail_address": GMAIL,
            "key_version": 1,
            "refresh_token_encrypted": "\\x00",
        },
    )
    account = svc(
        "POST",
        "accounts",
        json={"user_id": a["id"], "name": "Crédito", "kind": "credit", "last4": "1111"},
        headers={"Prefer": "return=representation"},
    )
    return a["id"], account[0]["id"]


def alert_email(key: str, text: str | None = None) -> bytes:
    msg = EmailMessage()
    msg["Authentication-Results"] = (
        "mx.google.com; dkim=pass header.d=notificacionesbancolombia.com header.s=s1"
    )
    msg["From"] = (
        "Alertas y Notificaciones <alertasynotificaciones@notificacionesbancolombia.com>"
    )
    msg["Subject"] = "Alertas y Notificaciones"
    msg["Message-ID"] = f"<{uuid.uuid4()}@notificacionesbancolombia.com>"
    msg.set_content(text or ALERTS[key])
    return msg.as_bytes()


def invoice_email(key: str) -> bytes:
    path = next(SUP.glob(f"{key}_*.zip"))
    msg = EmailMessage()
    msg["Authentication-Results"] = "mx.google.com; dkim=pass header.d=comercio.example"
    msg["From"] = "Facturación <facturas@comercio.example>"
    msg["Subject"] = "900000001;COMERCIO EJEMPLO SAS;FE-1;01;COMERCIO EJEMPLO"
    msg["Message-ID"] = f"<{uuid.uuid4()}@comercio.example>"
    msg.set_content("Adjuntamos su factura electrónica.")
    msg.add_attachment(path.read_bytes(), "application", "zip", filename=path.name)
    return msg.as_bytes()


def txs(user_id):
    return svc(
        "GET",
        "transactions",
        params={
            "user_id": f"eq.{user_id}",
            "select": "amount::text,merchant,status,payment_method,invoice_cufe,account_id,source_ref",
        },
    )


def statuses(user_id):
    rows = svc(
        "GET", "inbound_emails", params={"user_id": f"eq.{user_id}", "select": "status"}
    )
    return sorted(r["status"] for r in rows)


def test_alert_then_invoice_is_one_completed_movement(env, caplog):
    import app.main  # noqa: F401 - aplica la configuración de logs del backend (httpx/httpcore en WARNING)

    caplog.set_level(logging.DEBUG)
    user_id, account_id = env
    assert ingest(user_id, alert_email("A02")) == "stored"
    assert ingest(user_id, invoice_email("F01")) == "stored"

    [tx] = txs(user_id)
    assert tx["amount"] == "45900.00" and tx["status"] == "confirmed"
    assert (
        tx["merchant"] == "SUPERMERCADO EJEMPLO SAS"
        and tx["payment_method"] == "credit_card"
    )
    assert tx["account_id"] == account_id and tx["source_ref"].startswith("bank:")
    assert re.fullmatch(r"[0-9a-f]{96}", tx["invoice_cufe"])
    assert statuses(user_id) == ["extracted", "extracted"]
    for secret in ("SUPERMERCADO", "45.900", "45900", GMAIL, "*1111"):
        assert secret not in caplog.text  # los logs solo llevan ids, plantilla y motivo


def test_invoice_then_alert_is_one_completed_movement(env):
    user_id, account_id = env
    assert ingest(user_id, invoice_email("F01")) == "stored"
    [tx] = txs(user_id)
    assert tx["status"] == "pending_review"  # tarjeta sin alerta del banco todavía

    assert ingest(user_id, alert_email("A02")) == "stored"
    [tx] = txs(user_id)
    assert tx["status"] == "confirmed" and tx["source_ref"].startswith("bank:")
    assert (
        tx["merchant"] == "SUPERMERCADO EJEMPLO SAS" and tx["account_id"] == account_id
    )
    assert tx["invoice_cufe"]


def test_review_and_no_movement_cases(env):
    user_id, _ = env
    for key in ("A11", "A12", "A04"):  # pago de la tarjeta, rechazada, USD
        assert ingest(user_id, alert_email(key)) == "stored"
    for key in ("F03", "F04", "F02"):  # débito sin alerta, otro comprador, efectivo
        assert ingest(user_id, invoice_email(key)) == "stored"

    rows = sorted(txs(user_id), key=lambda t: t["amount"])
    assert [(t["amount"], t["status"]) for t in rows] == [
        ("32000.00", "confirmed"),  # F02 efectivo: movimiento nuevo
        ("61250.00", "pending_review"),  # F03
    ]
    assert statuses(user_id) == [
        "extracted",  # A11
        "extracted",  # A12
        "extracted",  # F02
        "extracted",  # F03 (movimiento en revisión)
        "pending_review",  # A04 sin plantilla
        "pending_review",  # F04 comprador distinto
    ]


OUTSIDE = (
    "Bancolombia: Recibiste $120.000,00 de JUAN INVENTADO en tu cuenta de ahorros *2222 "
    "el {date} a las 08:12."
)


def test_alert_outside_templates_goes_through_llm_to_review(env, monkeypatch):
    from datetime import datetime

    from app.extract import llm

    user_id, _ = env
    today = datetime.now(llm.COLOMBIA).strftime("%d/%m/%Y")
    text = OUTSIDE.format(date=today)
    answer = {
        "amount": "$120.000,00",
        "direction": "income",
        "merchant": "JUAN INVENTADO",
        "date": today,
        "time": "08:12",
        "payment_method": "transfer",
        "last4": "2222",
    }
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(llm, "ask", lambda t, **kw: json.dumps(answer))
    assert ingest(user_id, alert_email("", text)) == "stored"

    monkeypatch.setattr(
        llm, "ask", lambda t, **kw: (_ for _ in ()).throw(httpx.ConnectError("caído"))
    )
    assert ingest(user_id, alert_email("", text.replace("08:12", "09:30"))) == "stored"

    [tx] = txs(user_id)  # solo el primero: el segundo no tiene datos
    assert (tx["amount"], tx["status"], tx["payment_method"]) == (
        "120000.00",
        "pending_review",
        "transfer",
    )
    assert statuses(user_id) == ["extracted", "pending_review"]


def test_llm_date_window_uses_the_email_arrival_not_now(env, monkeypatch):
    """Un reproceso días después no rechaza la fecha: la ventana se mide contra received_at."""
    from datetime import datetime, timedelta

    from app.extract import llm, pipeline
    from app.ingest import mail

    user_id, _ = env
    arrived = datetime.now(llm.COLOMBIA) - timedelta(days=10)
    day = arrived.strftime("%d/%m/%Y")
    text = OUTSIDE.format(date=day)
    answer = json.dumps(
        {
            "amount": "$120.000,00",
            "direction": "income",
            "merchant": "JUAN INVENTADO",
            "date": day,
            "time": "08:12",
            "payment_method": "transfer",
            "last4": "2222",
        }
    )
    # Contra "ahora" la misma respuesta se rechazaría (10 días > 3).
    assert llm.check(text, answer, datetime.now(llm.COLOMBIA)).reason == "fecha"

    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test")
    monkeypatch.setattr(llm, "ask", lambda t, **kw: answer)
    msg = mail.parse(alert_email("", text))
    email_id = str(uuid.uuid4())  # reproceso directo, sin fila previa en inbound_emails
    assert (
        pipeline.process(user_id, email_id, "bancolombia", msg, arrived) == "extracted"
    )
    [tx] = txs(user_id)
    assert (tx["amount"], tx["status"]) == ("120000.00", "pending_review")
