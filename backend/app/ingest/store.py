"""Recibe un correo crudo de un usuario y, si pasa el filtro, lo guarda cifrado (Paso 08).

Los logs solo llevan metadatos: nunca asunto, cuerpo, direcciones completas ni claves.
"""

import logging
from datetime import datetime

from app import push, service_db
from app.extract import pipeline
from app.ingest import crypto, mail

log = logging.getLogger("fsf.ingest")


def _aad(user_id: str, digest: str) -> bytes:
    return f"{user_id}:{digest}".encode()


def ingest(
    user_id: str,
    raw: bytes,
    source: str = "gmail",
    dedupe_key: str | None = None,
    received_ms: int | None = None,
) -> str:
    """Devuelve 'stored', 'duplicate', 'too_large' o el motivo del descarte ('no_rule', 'discarded', 'dkim').

    [dedupe_key] identifica el mensaje para no guardarlo dos veces (en Gmail, su id de mensaje);
    sin él se usa el Message-ID, que pone el remitente.
    """
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

    digest = mail.message_hash(msg, raw, dedupe_key)
    version, blob = crypto.encrypt(clean, _aad(user_id, digest))
    r = service_db.rest(
        "POST",
        "inbound_emails",
        params={"on_conflict": "user_id,message_hash", "select": "id,received_at"},
        prefer="resolution=ignore-duplicates,return=representation",
        json={
            "user_id": user_id,
            "source": source,
            "rule": decision.rule,
            "sender_domain": decision.sender_domain,
            "message_hash": digest,
            "key_version": version,
            "raw_encrypted": service_db.to_bytea(blob),
        },
    )
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
    try:
        pipeline.process(
            user_id,
            rows[0]["id"],
            decision.rule,
            msg,
            datetime.fromisoformat(rows[0]["received_at"]),
        )
    except Exception as e:  # noqa: BLE001 - el correo ya está guardado; un fallo no debe perderlo
        # Queda en pending_extraction. Solo el tipo: el mensaje podría llevar datos del correo.
        log.error("falló la extracción id=%s error=%s", rows[0]["id"], type(e).__name__)
    try:
        push.new_movements(
            user_id, received_ms
        )  # [received_ms]: cuándo lo recibió Gmail (RQN 04)
    except Exception as e:  # noqa: BLE001 - un aviso que falla no debe perder el correo
        log.error("falló el aviso id=%s error=%s", rows[0]["id"], type(e).__name__)
    return "stored"
