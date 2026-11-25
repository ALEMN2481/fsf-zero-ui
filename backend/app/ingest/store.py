"""Recibe un correo crudo de un usuario y, si pasa el filtro, lo guarda cifrado (Paso 08).

Los logs solo llevan metadatos: nunca asunto, cuerpo, direcciones completas ni claves.
"""

import logging

import httpx

from app.config import settings
from app.ingest import crypto, mail

log = logging.getLogger("fsf.ingest")


def _aad(user_id: str, digest: str) -> bytes:
    return f"{user_id}:{digest}".encode()


def ingest(user_id: str, raw: bytes, source: str = "gmail") -> str:
    """Devuelve 'stored', 'duplicate', 'too_large' o el motivo del descarte ('no_rule', 'discarded', 'dkim')."""
    try:
        msg = mail.parse(raw)
    except ValueError:
        log.info("correo descartado motivo=too_large")
        return "too_large"

    decision = mail.classify(msg)
    if not decision.accepted:
        log.info(
            "correo descartado motivo=%s regla=%s dominio=%s",
            decision.reason,
            decision.rule,
            decision.sender_domain,
        )
        return decision.reason

    clean = mail.sanitize(msg, decision.rule)
    if len(clean) > mail.MAX_STORED_BYTES:
        log.info("correo descartado motivo=too_large regla=%s", decision.rule)
        return "too_large"

    digest = mail.message_hash(msg, raw)
    version, blob = crypto.encrypt(clean, _aad(user_id, digest))
    r = httpx.post(
        f"{settings.supabase_url}/rest/v1/inbound_emails",
        params={"on_conflict": "user_id,message_hash", "select": "id"},
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Prefer": "resolution=ignore-duplicates,return=representation",
        },
        json={
            "user_id": user_id,
            "source": source,
            "rule": decision.rule,
            "sender_domain": decision.sender_domain,
            "message_hash": digest,
            "key_version": version,
            "raw_encrypted": "\\x" + blob.hex(),
        },
        timeout=10,
    )
    if r.status_code not in (200, 201):
        log.error(
            "no se pudo guardar el correo status=%s regla=%s",
            r.status_code,
            decision.rule,
        )
        r.raise_for_status()
    rows = r.json()
    if not rows:
        log.info("correo duplicado regla=%s", decision.rule)
        return "duplicate"
    log.info(
        "correo guardado id=%s regla=%s dominio=%s",
        rows[0]["id"],
        decision.rule,
        decision.sender_domain,
    )
    return "stored"
