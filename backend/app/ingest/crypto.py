"""Cifrado AES-256-GCM de los correos guardados, con versión de clave para poder rotarla."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

NONCE_BYTES = 12


def _keys() -> dict[int, bytes]:
    keys: dict[int, bytes] = {}
    for item in filter(None, (p.strip() for p in settings.email_keys.split(","))):
        version, _, b64 = item.partition(":")
        key = base64.b64decode(b64)
        if len(key) != 32:
            raise ValueError(f"La clave de correos v{version} no mide 32 bytes")
        keys[int(version)] = key
    if not keys:
        raise RuntimeError("Falta EMAIL_KEYS en backend/.env")
    return keys


def encrypt(plaintext: bytes, aad: bytes) -> tuple[int, bytes]:
    """Cifra con la versión de clave más alta. [aad] ata el texto cifrado a su fila (usuario + hash)."""
    keys = _keys()
    version = max(keys)
    nonce = os.urandom(NONCE_BYTES)
    return version, nonce + AESGCM(keys[version]).encrypt(nonce, plaintext, aad)


def decrypt(version: int, blob: bytes, aad: bytes) -> bytes:
    key = _keys()[version]  # KeyError si la versión ya no está configurada
    return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
