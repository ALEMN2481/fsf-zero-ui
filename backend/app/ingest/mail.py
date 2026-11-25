"""Filtro de correos: qué remitentes se aceptan, verificación DKIM y limpieza antes de guardar.

Solo decide y prepara: no extrae montos ni comercios (eso es del Paso 09).
"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr

# Solo se confía en el Authentication-Results que Gmail añade arriba de todo al recibir.
TRUSTED_AUTHSERV = "mx.google.com"
MAX_STORED_BYTES = 5 * 1024 * 1024
MAX_PARSED_BYTES = 30 * 1024 * 1024  # Gmail no entrega correos más grandes de ~25 MB


@dataclass(frozen=True)
class Rule:
    name: str
    sender: str  # dirección exacta del remitente
    dkim_domain: str  # dominio que debe firmar (DKIM header.d)
    discard: bool = False  # se reconoce pero no se guarda


# Remitentes confirmados. Otros bancos se añaden al confirmar sus cabeceras con correos reales.
BANK_RULES = (
    Rule(
        "bancolombia",
        "alertasynotificaciones@notificacionesbancolombia.com",
        "notificacionesbancolombia.com",
    ),
    # Confirmaciones de seguridad, no movimientos.
    Rule(
        "bancolombia_seguridad",
        "validaciondeseguridad@notificacionesbancolombia.com",
        "notificacionesbancolombia.com",
        discard=True,
    ),
)
INVOICE_RULE = "factura_electronica"

# Asunto de la factura electrónica (DIAN): NIT;Nombre;Número;Tipo de documento;... con tipo 01 = factura.
_INVOICE_SUBJECT = re.compile(r"^\s*\d[\d.\-]*\s*;[^;]+;[^;]+;\s*01\s*;")
_DKIM_RESULT = re.compile(r"^dkim\s*=\s*(\w+)", re.IGNORECASE)
_HEADER_D = re.compile(r"\bheader\.d\s*=\s*([^\s;]+)", re.IGNORECASE)
_HEADER_I = re.compile(r"\bheader\.i\s*=\s*[^@\s;]*@([^\s;]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str  # 'stored-candidate', 'no_rule', 'discarded', 'dkim'
    rule: str | None = None
    sender_domain: str = ""


def parse(raw: bytes) -> EmailMessage:
    if len(raw) > MAX_PARSED_BYTES:
        raise ValueError("Correo demasiado grande")
    return BytesParser(policy=policy.default).parsebytes(raw)  # type: ignore[return-value]


def dkim_pass_domains(msg: EmailMessage) -> set[str]:
    """Dominios con dkim=pass según el Authentication-Results de mx.google.com que está arriba de todo.

    Las cabeceras de más abajo las puede escribir cualquiera (el remitente) y se ignoran.
    """
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return set()
    authserv, _, results = str(headers[0]).partition(";")
    if authserv.strip().lower() != TRUSTED_AUTHSERV:
        return set()
    domains = set()
    for result in results.split(";"):
        result = result.strip()
        status = _DKIM_RESULT.match(result)
        if not status or status.group(1).lower() != "pass":
            continue
        # Gmail suele informar header.i=@dominio; se acepta header.d si viene.
        found = _HEADER_D.search(result) or _HEADER_I.search(result)
        if found:
            domains.add(found.group(1).lower().rstrip("."))
    return domains


def _aligned(signer: str, domain: str) -> bool:
    return signer == domain or domain.endswith("." + signer)


def _has_invoice_xml(msg: EmailMessage) -> bool:
    for part in msg.iter_attachments():
        name = (part.get_filename() or "").lower()
        data = part.get_payload(decode=True) or b""
        if name.endswith(".xml"):
            return True
        if name.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if any(n.lower().endswith(".xml") for n in z.namelist()):
                        return True
            except zipfile.BadZipFile:
                continue
    return False


def classify(msg: EmailMessage) -> Decision:
    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    domain = sender.rpartition("@")[2]
    signers = dkim_pass_domains(msg)

    for rule in BANK_RULES:
        if sender == rule.sender:
            if rule.discard:
                return Decision(False, "discarded", rule.name, domain)
            if rule.dkim_domain not in signers:
                return Decision(False, "dkim", rule.name, domain)
            return Decision(True, "stored-candidate", rule.name, domain)

    if _INVOICE_SUBJECT.match(str(msg.get("Subject", ""))) and _has_invoice_xml(msg):
        # Las facturas llegan de cualquier comercio: la firma debe ser del dominio del remitente.
        if not any(_aligned(s, domain) for s in signers):
            return Decision(False, "dkim", INVOICE_RULE, domain)
        return Decision(True, "stored-candidate", INVOICE_RULE, domain)

    return Decision(False, "no_rule", None, domain)


def sanitize(msg: EmailMessage, rule: str) -> bytes:
    """Quita adjuntos innecesarios: los bancos no guardan ninguno; las facturas, solo .zip y .xml."""
    keep_ext = (".zip", ".xml") if rule == INVOICE_RULE else ()

    def keep(p: EmailMessage) -> bool:
        name = (p.get_filename() or "").lower()
        if p.is_multipart() or not (p.is_attachment() or name):
            return True  # contenedores y cuerpo del correo
        return bool(keep_ext) and name.endswith(keep_ext)

    for part in msg.walk():
        if part.is_multipart():
            part.set_payload([p for p in part.get_payload() if keep(p)])
    return msg.as_bytes()


def message_hash(msg: EmailMessage, raw: bytes, dedupe_key: str | None = None) -> str:
    key = dedupe_key or str(msg.get("Message-ID", "")).strip().lower()
    return hashlib.sha256(key.encode() if key else raw).hexdigest()


# Carpetas de Gmail que nunca se leen, aunque el correo coincida con una regla.
EXCLUDED_LABELS = frozenset({"SENT", "DRAFT", "TRASH"})
# D8: los bancos se aceptan también desde Spam (DKIM del banco frena la suplantación); las facturas
# solo desde la bandeja de entrada (el phishing con "facturas" y .zip puede tener DKIM de su dominio).
ALLOWED_LABELS = {"bank": frozenset({"INBOX", "SPAM"}), "invoice": frozenset({"INBOX"})}


def candidate_kind(from_header: str, subject: str) -> str | None:
    """Prefiltro con solo De y Asunto: 'bank', 'invoice' o None (no se descarga el correo completo)."""
    sender = parseaddr(from_header)[1].lower()
    if any(sender == r.sender and not r.discard for r in BANK_RULES):
        return "bank"
    return "invoice" if _INVOICE_SUBJECT.match(subject) else None


def allowed_location(kind: str, labels: list[str]) -> bool:
    """Según las etiquetas actuales de Gmail: ¿se puede leer este tipo de correo desde ahí?"""
    found = set(labels)
    return not (found & EXCLUDED_LABELS) and bool(found & ALLOWED_LABELS[kind])
