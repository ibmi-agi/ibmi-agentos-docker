"""
Credential Encryption
=====================

Fernet symmetric encryption for storing IBM i credentials at rest.

Uses ``AUTH_ENCRYPTION_KEY`` env var (base64-encoded 32-byte key).
Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import logging
from functools import lru_cache
from os import getenv

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Return a cached Fernet instance from the ``AUTH_ENCRYPTION_KEY`` env var."""
    key = getenv("AUTH_ENCRYPTION_KEY", "")
    if not key:
        raise EncryptionError(
            "AUTH_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string. Returns a URL-safe base64-encoded token."""
    try:
        return _get_fernet().encrypt(plaintext.encode()).decode()
    except Exception as exc:
        raise EncryptionError(f"Encryption failed: {exc}") from exc


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a previously encrypted credential string."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Decryption failed — invalid token or wrong encryption key") from exc
    except Exception as exc:
        raise EncryptionError(f"Decryption failed: {exc}") from exc
