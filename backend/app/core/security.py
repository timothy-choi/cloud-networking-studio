"""Password hashing and JWT helpers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALG = "HS256"

_BCRYPT_MAX_BYTES = 72


def _normalize_for_bcrypt(plain: str) -> str:
    """Bcrypt only accepts the first 72 UTF-8 bytes of a secret. Longer passwords are pre-hashed.

    Same normalization is applied in ``hash_password`` and ``verify_password`` so round-trips match.
    """
    raw = plain.encode("utf-8")
    if len(raw) <= _BCRYPT_MAX_BYTES:
        return plain
    return hashlib.sha256(raw).hexdigest()


def hash_password(plain: str) -> str:
    """Hash a password for storage. Input is normalized to satisfy bcrypt's 72-byte limit."""
    return pwd_context.hash(_normalize_for_bcrypt(plain))


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(_normalize_for_bcrypt(plain), password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.auth_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.auth_secret_key, algorithms=[JWT_ALG])
