"""Paso 09 (D9): servidor MCP de demostración, probado con un cliente MCP en memoria."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.config import settings
from app.extract import llm

A02 = (
    "Bancolombia: Compraste $45.900,00 en SUPERMERCADO EJEMPLO SAS con tu T.Cred *1111, "
    "el 24/11/2026 a las 10:23. Si tienes dudas, encuentranos aqui: 000 000 0000."
)
OUTSIDE = (
    "Bancolombia: Recibiste $120.000,00 de JUAN INVENTADO en tu cuenta de ahorros *2222 "
    "el 19/11/2026 a las 08:12."
)


@pytest.fixture(scope="module")
def server():
    saved = (
        settings.model_dump()
    )  # importar el servidor vacía los secretos: se restauran al final
    from app import mcp_server

    yield mcp_server.mcp
    for name, value in saved.items():
        setattr(settings, name, value)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def call(server, tool, args):
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(tool, args)
    return result.isError, (
        json.loads(result.content[0].text)
        if not result.isError
        else result.content[0].text
    )


@pytest.mark.anyio
async def test_lists_exactly_the_two_tools(server):
    async with create_connected_server_and_client_session(server) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
    assert tools == {"extract_bank_alert", "parse_amount"}


@pytest.mark.anyio
async def test_alert_that_fits_a_template_is_confirmed(server):
    err, r = await call(server, "extract_bank_alert", {"text": A02})
    assert not err
    assert (r["status"], r["source"], r["template"]) == (
        "confirmed",
        "plantilla",
        "compra",
    )
    assert (r["amount"], r["merchant"], r["last4"]) == (
        "45900.00",
        "SUPERMERCADO EJEMPLO SAS",
        "1111",
    )
    assert r["occurred_at"] == "2026-11-24T10:23:00-05:00"


@pytest.mark.anyio
async def test_card_payment_is_no_movement(server):
    text = "Bancolombia: Pagaste $500.000,00 a tu T.Cred *1111 desde tu cuenta *2222, el 16/11/2026 a las 12:00."
    _, r = await call(server, "extract_bank_alert", {"text": text})
    assert (r["status"], r["amount"]) == ("no_movement", None)


@pytest.mark.anyio
async def test_alert_outside_templates_uses_llm_and_stays_in_review(
    server, monkeypatch
):
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:11434")
    answer = {
        "amount": "$120.000,00",
        "direction": "income",
        "merchant": "JUAN INVENTADO",
        "date": "19/11/2026",
        "time": "08:12",
        "payment_method": "transfer",
        "last4": "2222",
    }
    monkeypatch.setattr(llm, "ask", lambda t, **kw: json.dumps(answer))
    _, r = await call(
        server,
        "extract_bank_alert",
        {"text": OUTSIDE, "received_at": "2026-11-19T08:13:00-05:00"},
    )
    assert (r["status"], r["source"], r["amount"], r["direction"]) == (
        "pending_review",
        "llm",
        "120000.00",
        "income",
    )


@pytest.mark.anyio
async def test_without_llm_the_state_is_still_reported(server):
    _, r = await call(
        server, "extract_bank_alert", {"text": OUTSIDE}
    )  # conftest desactiva el LLM
    assert (r["status"], r["source"], r["reason"], r["amount"]) == (
        "pending_review",
        "llm",
        "llm_desactivado",
        None,
    )


@pytest.mark.anyio
async def test_parse_amount(server):
    assert await call(server, "parse_amount", {"text": "$1.234.567,89"}) == (
        False,
        {"amount": "1234567.89"},
    )
    err, message = await call(server, "parse_amount", {"text": "1.2345"})
    assert err and "monto no reconocido" in message


def test_server_process_has_no_secrets_no_db_and_only_local_network(tmp_path):
    """Como se ejecuta de verdad: proceso propio, con secretos y una URL externa en el entorno."""
    probe = (
        "import sys, app.mcp_server\n"
        "from app.config import settings as s\n"
        "print(s.supabase_service_role_key == '' and s.email_keys == '' and s.google_oauth_client_secret == '')\n"
        "print(s.ollama_url == '')\n"
        "print('app.service_db' in sys.modules or 'app.extract.pipeline' in sys.modules)\n"
    )
    env = {
        **os.environ,
        "SUPABASE_SERVICE_ROLE_KEY": "secreto-de-prueba",
        "EMAIL_KEYS": "1:secreto",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secreto",
        "OLLAMA_URL": "http://ollama.example.com:11434",
    }
    out = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parent.parent,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out == [
        "True",
        "True",
        "False",
    ]  # sin secretos · URL externa desactivada · sin BD
