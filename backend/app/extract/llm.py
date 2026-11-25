"""LLM local de respaldo (Paso 09C, D9): solo para alertas que no encajan en ninguna plantilla.

El LLM solo extrae; nunca calcula. Su salida pasa por un esquema Pydantic estricto y por
comprobaciones contra el texto del correo (el monto y los 4 dígitos deben aparecer tal cual, un
único monto en COP, comercio presente, fecha a ±3 días de la recepción). Aun así, todo lo que
devuelve queda en 'pending_review': en las pruebas confundió gasto/ingreso y el medio de pago.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.extract.amounts import parse_cop
from app.extract.bancolombia import _FOLD, COLOMBIA, Alert

log = logging.getLogger("fsf.extract")

MAX_TEXT = 2000  # caracteres del correo que se envían al modelo
DATE_WINDOW = timedelta(days=3)


class LlmMovement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: str = Field(max_length=30)
    direction: Literal["expense", "income"]
    merchant: str | None = Field(max_length=80)
    date: str = Field(pattern=r"^\d{2}/\d{2}/\d{4}$")
    time: str | None = Field(pattern=r"^\d{2}:\d{2}$")
    payment_method: Literal["credit_card", "debit_card", "transfer", "cash", "other"]
    last4: str | None = Field(pattern=r"^\d{4}$")


SCHEMA = LlmMovement.model_json_schema()

SYSTEM = """Extraes UN movimiento de una alerta bancaria colombiana y respondes solo con JSON.
- amount: el monto exactamente como aparece en el texto, con su símbolo (p. ej. "$45.900,00").
- direction: "expense" si el dinero sale del usuario (compra, pago, retiro, avance, transferencia
  o envío a otra persona); "income" si entra (transferencia recibida, abono, devolución, nómina).
- merchant: el comercio o la persona de la otra parte, copiado del texto; null si no hay.
- date: DD/MM/AAAA. time: HH:MM o null si no aparece.
- payment_method: "credit_card" (T.Cred, tarjeta de crédito), "debit_card" (T.Deb, tarjeta débito),
  "transfer" (desde o hacia una cuenta, PSE, QR, llave), "cash" o "other".
- last4: los 4 dígitos tras el * de la tarjeta o cuenta DEL USUARIO (no la de destino); null si no hay."""

# Ejemplos cortos inventados (punto 11): una compra → expense y una transferencia recibida → income.
EXAMPLES = (
    (
        "Bancolombia: compra de $12.300,00 en LIBRERIA INVENTADA con T.Cred *4321 el 02/01/2026 a las 09:15.",
        (
            '{"amount": "$12.300,00", "direction": "expense", "merchant": "LIBRERIA INVENTADA", '
            '"date": "02/01/2026", "time": "09:15", "payment_method": "credit_card", "last4": "4321"}'
        ),
    ),
    (
        "Bancolombia: te llegaron $70.000,00 de ANA INVENTADA a tu cuenta *8765 el 03/01/2026.",
        (
            '{"amount": "$70.000,00", "direction": "income", "merchant": "ANA INVENTADA", '
            '"date": "03/01/2026", "time": null, "payment_method": "transfer", "last4": "8765"}'
        ),
    ),
    (
        "Bancolombia: pagaste $40.000,00 desde tu cuenta *8765 a la cuenta *1000 el 04/01/2026 a las 18:00.",
        (
            '{"amount": "$40.000,00", "direction": "expense", "merchant": null, '
            '"date": "04/01/2026", "time": "18:00", "payment_method": "transfer", "last4": "8765"}'
        ),
    ),
)
USE_EXAMPLES = False  # medido (punto 11): con qwen2.5:3b los ejemplos no mejoran y restan un acierto


def prompt(text: str, examples: bool = USE_EXAMPLES) -> str:
    shots = (
        "".join(f"Alerta: {a}\nJSON: {j}\n\n" for a, j in EXAMPLES) if examples else ""
    )
    return f"{shots}Alerta: {text}\nJSON:"


def ask(text: str, *, model: str | None = None, examples: bool = USE_EXAMPLES) -> str:
    """Llama a Ollama y devuelve el JSON en texto (sin validar). Lanza httpx.HTTPError."""
    r = httpx.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": model or settings.ollama_model,
            "system": SYSTEM,
            "prompt": prompt(text, examples),
            "format": SCHEMA,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {"temperature": 0},
        },
        timeout=settings.ollama_timeout,
    )
    r.raise_for_status()
    return r.json()["response"]


def preload() -> None:
    """Carga el modelo en memoria al arrancar (sin prompt). Si Ollama no está, solo avisa."""
    if not settings.ollama_url:
        return
    try:
        httpx.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "keep_alive": settings.ollama_keep_alive,
            },
            timeout=settings.ollama_timeout,
        ).raise_for_status()
        log.info(
            "modelo precargado modelo=%s keep_alive=%s",
            settings.ollama_model,
            settings.ollama_keep_alive,
        )
    except httpx.HTTPError as e:
        log.warning("no se pudo precargar el modelo error=%s", type(e).__name__)


# ---------------------------------------------------------------- comprobaciones contra el texto
_COP_AMOUNT = re.compile(r"(?:\$|\bcop(?![a-z]))\s?(\d(?:[\d.,]*\d)?)", re.IGNORECASE)
# Otra moneda, también pegada al número ("USD15,99"): solo COP en el MVP.
_FOREIGN = re.compile(r"\b(?:usd|eur|mxn)(?![a-z])|us\$|€", re.IGNORECASE)


def _amounts_in(text: str) -> set:
    found = set()
    for raw in _COP_AMOUNT.findall(text):
        try:
            found.add(parse_cop(raw))
        except ValueError:
            continue
    return found


def check(text: str, raw_json: str, received_at: datetime) -> Alert:
    """Valida la respuesta del LLM. → Alert 'pending_review' con datos, o 'failed' con el motivo."""

    def fail(reason: str) -> Alert:
        return Alert("failed", reason, "llm")

    text = " ".join(text.split())
    try:
        m = LlmMovement.model_validate_json(raw_json)
    except ValidationError:
        return fail("esquema")
    if _FOREIGN.search(text):
        return fail("moneda")
    try:
        amount = parse_cop(m.amount)
    except ValueError:
        return fail("monto")
    in_text = _amounts_in(text)
    if in_text != {
        amount
    }:  # el monto debe estar en el texto y ser el único (p. ej. sin "saldo")
        return fail("monto_no_coincide" if amount not in in_text else "varios_montos")
    if m.last4 and not re.search(rf"\*\s?{m.last4}\b", text):
        return fail("last4")
    merchant = m.merchant.strip() if m.merchant else None
    if merchant and merchant.casefold().translate(
        _FOLD
    ) not in text.casefold().translate(_FOLD):
        return fail("comercio")
    try:
        when = datetime.strptime(f"{m.date} {m.time or '00:00'}", "%d/%m/%Y %H:%M")
    except ValueError:
        return fail("fecha")
    when = when.replace(tzinfo=COLOMBIA)
    if abs(when - received_at) > DATE_WINDOW:
        return fail("fecha")
    return Alert(
        "pending_review",
        "llm",
        "llm",
        direction=m.direction,
        amount=amount,
        merchant=merchant or None,
        occurred_at=when,
        payment_method=m.payment_method,
        last4=m.last4,
    )


def extract(text: str, received_at: datetime) -> Alert:
    if not settings.ollama_url:
        return Alert("failed", "llm_desactivado", "llm")
    text = " ".join(text.split())[:MAX_TEXT]
    try:
        raw = ask(text)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("llm no disponible error=%s", type(e).__name__)
        return Alert("failed", "llm_no_disponible", "llm")
    return check(text, raw, received_at)
