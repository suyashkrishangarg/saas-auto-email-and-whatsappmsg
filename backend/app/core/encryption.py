"""AES-256 style envelope encryption for DB secrets.

Uses Fernet (AES-128-CBC + HMAC-SHA256 over a 256-bit key) which provides
authenticated encryption at rest. All tokens/keys marked `is_secret` on
SystemSetting pass through this helper before hitting PostgreSQL.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _derive_key(raw: str) -> bytes:
    """Accept any developer-supplied string and turn it into a valid 32-byte Fernet key.

    If the operator supplied a proper urlsafe-base64 32-byte key we use it verbatim.
    """
    try:
        decoded = base64.urlsafe_b64decode(raw.encode())
        if len(decoded) == 32:
            return raw.encode()
    except Exception:
        pass
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _fernet() -> Fernet:
    return Fernet(_derive_key(settings.FERNET_KEY))


def encrypt(value: str) -> str:
    if value is None:
        return value
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if token is None:
        return token
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # key rotation or plaintext legacy value -> return as-is
        return token


def encrypt_or_none(value):
    return None if value is None else encrypt(value)


def decrypt_or_none(value):
    return None if value is None else decrypt(value)
