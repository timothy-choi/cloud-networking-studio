"""Encrypt/decrypt credential profile secrets at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    raw = (settings.credential_encryption_key or settings.auth_secret_key).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("Secret material is required.")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        raise ValueError("Encrypted secret is missing.")
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt credential profile secret.") from exc
