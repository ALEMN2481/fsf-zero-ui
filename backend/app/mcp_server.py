"""Servidor MCP mínimo para la demostración (Paso 09, D9). Transporte stdio.

    cd backend && .venv/Scripts/python.exe -m app.mcp_server

Fuera del camino real del correo: envuelve el mismo módulo de extracción, pero solo procesa el
texto que recibe. Sin base de datos (no importa service_db ni pipeline), sin secretos (no lee
backend/.env y vacía cualquier clave que llegue por el entorno) y sin red salvo un Ollama local.
"""

import os

os.environ["FSF_ENV_FILE"] = ""  # antes de importar app.config: no se lee backend/.env

from datetime import datetime
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.extract import llm
from app.extract.amounts import parse_cop
from app.extract.bancolombia import COLOMBIA, Alert, parse_alert

# Ningún secreto en este proceso, aunque venga por variables de entorno.
for _name in type(settings).model_fields:
    if (
        _name.startswith(("supabase_", "google_", "gmail_", "pubsub_"))
        or _name == "email_keys"
    ):
        setattr(settings, _name, "")
# Red: solo un Ollama en esta máquina; cualquier otra URL desactiva el respaldo con LLM.
if urlparse(settings.ollama_url).hostname not in ("127.0.0.1", "localhost", "::1"):
    settings.ollama_url = ""

mcp = FastMCP("finanzas-sin-filtro-extraccion")


def _result(alert: Alert, source: str) -> dict:
    # 'failed' (el LLM no dio datos válidos) se presenta como revisión: no hay movimiento que confirmar.
    status = "pending_review" if alert.status == "failed" else alert.status
    return {
        "status": status,
        "source": source,
        "reason": alert.reason,
        "template": alert.template,
        "direction": alert.direction,
        "amount": str(alert.amount) if alert.amount is not None else None,
        "merchant": alert.merchant,
        "occurred_at": alert.occurred_at.isoformat() if alert.occurred_at else None,
        "payment_method": alert.payment_method,
        "last4": alert.last4,
    }


@mcp.tool()
def extract_bank_alert(text: str, received_at: str | None = None) -> dict:
    """Extrae el movimiento de una alerta de Bancolombia.

    Primero con las plantillas fijas; si no encaja ninguna, con el LLM local (cuyo resultado
    siempre queda en pending_review). status: confirmed | pending_review | no_movement.
    received_at (ISO 8601, opcional): llegada del correo, para la ventana de fechas del LLM.
    """
    alert = parse_alert(text)
    if alert.reason != "sin_plantilla":
        return _result(alert, "plantilla")
    when = (
        datetime.fromisoformat(received_at) if received_at else datetime.now(COLOMBIA)
    )
    if when.tzinfo is None:
        when = when.replace(tzinfo=COLOMBIA)
    return _result(llm.extract(text, when), "llm")


@mcp.tool()
def parse_amount(text: str) -> dict:
    """Convierte un monto colombiano ('$1.234.567,89', 'COP 50.000') a decimal con 2 cifras.

    Error si no es un monto positivo válido en COP.
    """
    return {"amount": str(parse_cop(text))}


if __name__ == "__main__":
    mcp.run()  # stdio
