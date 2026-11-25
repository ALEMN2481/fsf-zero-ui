"""Factura electrónica DIAN: .zip → AttachedDocument → Invoice + ApplicationResponse (Paso 09A).

Lectura determinista, sin LLM. Una factura queda 'confirmed' solo si la DIAN la validó
(comprobación estructural: ResponseCode de validación y el mismo CUFE en la factura y en la
respuesta) y va dirigida al usuario (correo del comprador = Gmail conectado). Si no,
'pending_review'. La firma XAdES no se verifica aquí: Paso 15 (riesgo anotado).
"""

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

# ---------------------------------------------------------------- límites del .zip
MAX_FILES = 10
MAX_UNCOMPRESSED = 5 * 1024 * 1024  # bytes, suma de los XML leídos
MAX_RATIO = 100  # descomprimido / comprimido

# ---------------------------------------------------------------- estructura (Anexo Técnico, UBL 2.1)
# Todo lo que depende del formato real de la DIAN está aquí, para ajustarlo con una factura real.
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
ROOT_ATTACHED = (
    "{urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2}AttachedDocument"
)
ROOT_INVOICE = "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice"
ROOT_RESPONSE = "{urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2}ApplicationResponse"
PATH_INVOICE = "cac:Attachment/cac:ExternalReference/cbc:Description"
PATH_RESPONSE = (
    "cac:ParentDocumentLineReference/cac:DocumentReference"
    "/cac:Attachment/cac:ExternalReference/cbc:Description"
)
INV_NUMBER = "cbc:ID"
INV_CUFE = "cbc:UUID"
INV_DATE = "cbc:IssueDate"
INV_TIME = "cbc:IssueTime"
INV_SUPPLIER_NAME = (
    "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:RegistrationName"
)
INV_SUPPLIER_NIT = (
    "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID"
)
INV_BUYER_EMAIL = "cac:AccountingCustomerParty/cac:Party/cac:Contact/cbc:ElectronicMail"
INV_TOTAL = "cac:LegalMonetaryTotal/cbc:PayableAmount"
INV_PAYMENT = "cac:PaymentMeans/cbc:PaymentMeansCode"
RESP_CODE = "cac:DocumentResponse/cac:Response/cbc:ResponseCode"
RESP_CUFE = "cac:DocumentResponse/cac:DocumentReference/cbc:UUID"
DIAN_VALIDATED = {
    "02"
}  # "Documento validado por la DIAN": confirmar con una factura real
# Tabla de medios de pago del Anexo; un código desconocido queda como 'other' (9B → pending_review).
PAYMENT_MEANS = {
    "10": "cash",
    "48": "credit_card",
    "49": "debit_card",
    "42": "transfer",
    "47": "transfer",
}
COLOMBIA = timezone(timedelta(hours=-5))  # si IssueTime viene sin zona
CUFE_RE = re.compile(r"[0-9a-f]{96}")  # SHA-384 en hexadecimal


class InvoiceError(Exception):
    """El .zip o el XML no se pueden leer con seguridad; el mensaje es el motivo (sin datos)."""


@dataclass(frozen=True)
class Invoice:
    number: str
    cufe: str
    issued_at: datetime
    supplier_name: str
    supplier_nit: str
    buyer_emails: tuple[str, ...]
    total: Decimal
    currency: str
    payment_method: str  # cash | credit_card | debit_card | transfer | other


@dataclass(frozen=True)
class InvoiceCheck:
    status: str  # confirmed | pending_review
    reason: str | None
    invoice: Invoice | None


# ---------------------------------------------------------------- .zip
def read_invoice_zip(data: bytes) -> bytes:
    """Devuelve el único XML del .zip, leído en memoria y con límites."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InvoiceError("zip_invalido") from None
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise InvoiceError("zip_demasiados_archivos")
    xmls, total = [], 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in PurePosixPath(name).parts or ":" in name:
            raise InvoiceError("zip_ruta_peligrosa")
        if info.is_dir():
            continue
        if name.lower().endswith(".zip"):
            raise InvoiceError("zip_anidado")
        if info.flag_bits & 0x1:
            raise InvoiceError("zip_cifrado")
        if not name.lower().endswith(".xml"):
            continue  # el PDF de representación gráfica no se lee
        # Se lee como mucho hasta el límite: el tamaño declarado en la cabecera puede mentir.
        with zf.open(info) as f:
            content = f.read(MAX_UNCOMPRESSED - total + 1)
        total += len(content)
        if total > MAX_UNCOMPRESSED:
            raise InvoiceError("zip_demasiado_grande")
        if len(content) > MAX_RATIO * max(info.compress_size, 1):
            raise InvoiceError("zip_compresion_sospechosa")
        xmls.append(content)
    if len(xmls) != 1:
        raise InvoiceError("zip_sin_un_xml")
    return xmls[0]


# ---------------------------------------------------------------- XML
def _parse(xml: bytes | str, root_tag: str) -> Element:
    try:
        root = fromstring(xml, forbid_dtd=True)
    except DefusedXmlException:
        raise InvoiceError("xml_inseguro") from None
    except (ParseError, ValueError):
        raise InvoiceError("xml_invalido") from None
    if root.tag != root_tag:
        raise InvoiceError("xml_tipo_inesperado")
    return root


def _text(node: Element, path: str, required: bool = True) -> str:
    found = node.find(path, NS)
    value = (found.text or "").strip() if found is not None else ""
    if required and not value:
        raise InvoiceError(f"xml_falta:{path.rsplit(':', 1)[-1]}")
    return value


def _emails(node: Element) -> tuple[str, ...]:
    raw = " ".join((e.text or "") for e in node.findall(INV_BUYER_EMAIL, NS))
    return tuple(normalize_email(e) for e in re.split(r"[;,\s]+", raw) if "@" in e)


def normalize_email(address: str) -> str:
    """Minúsculas; en Gmail, sin puntos ni '+etiqueta' en la parte local (son el mismo buzón)."""
    local, _, domain = address.strip().casefold().rpartition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.split("+", 1)[0].replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def _invoice(root: Element) -> Invoice:
    total_node = root.find(INV_TOTAL, NS)
    try:
        total = Decimal(_text(root, INV_TOTAL)).quantize(Decimal("0.01"))
        issued_at = datetime.fromisoformat(
            f"{_text(root, INV_DATE)}T{_text(root, INV_TIME)}"
        )
    except (InvalidOperation, ValueError):
        raise InvoiceError("xml_valor_invalido") from None
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=COLOMBIA)
    if not total.is_finite() or total <= 0:
        raise InvoiceError("xml_valor_invalido")
    codes = {(c.text or "").strip() for c in root.findall(INV_PAYMENT, NS)}
    return Invoice(
        number=_text(root, INV_NUMBER),
        cufe=_text(root, INV_CUFE).casefold(),
        issued_at=issued_at,
        supplier_name=_text(root, INV_SUPPLIER_NAME),
        supplier_nit=_text(root, INV_SUPPLIER_NIT),
        buyer_emails=_emails(root),
        total=total,
        currency=(total_node.get("currencyID") or "").upper(),
        payment_method=PAYMENT_MEANS.get(codes.pop(), "other")
        if len(codes) == 1
        else "other",
    )


def parse_attached_document(xml: bytes) -> tuple[Invoice, str, str]:
    """→ (factura, ResponseCode de la DIAN, CUFE del ApplicationResponse)."""
    root = _parse(xml, ROOT_ATTACHED)
    invoice = _invoice(_parse(_text(root, PATH_INVOICE), ROOT_INVOICE))
    response = _parse(_text(root, PATH_RESPONSE), ROOT_RESPONSE)
    return invoice, _text(response, RESP_CODE), _text(response, RESP_CUFE).casefold()


# ---------------------------------------------------------------- decisión
def check_invoice(zip_bytes: bytes, gmail_address: str) -> InvoiceCheck:
    try:
        invoice, code, response_cufe = parse_attached_document(
            read_invoice_zip(zip_bytes)
        )
    except InvoiceError as e:
        return InvoiceCheck("pending_review", str(e), None)
    if not CUFE_RE.fullmatch(invoice.cufe):
        return InvoiceCheck("pending_review", "cufe_formato", invoice)
    if code not in DIAN_VALIDATED or response_cufe != invoice.cufe:
        return InvoiceCheck("pending_review", "dian_no_validada", invoice)
    if normalize_email(gmail_address) not in invoice.buyer_emails:
        return InvoiceCheck("pending_review", "comprador_distinto", invoice)
    if invoice.currency != "COP":
        return InvoiceCheck("pending_review", "moneda", invoice)
    return InvoiceCheck("confirmed", None, invoice)
