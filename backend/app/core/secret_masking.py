"""Redact secrets from logs, audit metadata, and error messages (Step 53D)."""

from __future__ import annotations

import re
from typing import Any

# JWT: header.payload.signature
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
# Personal API token: uuid.secret
_API_TOKEN_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[A-Za-z0-9_-]{8,}\b",
    re.IGNORECASE,
)
# Common env secret assignments in error strings
_ENV_SECRET_PATTERN = re.compile(
    r"(?i)((?:auth_secret_key|password|secret|api_key|token)\s*[=:]\s*)(\S+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)(\S+)")


def mask_secrets_in_text(text: str | None) -> str | None:
    if text is None:
        return None
    if not text:
        return text
    out = _JWT_PATTERN.sub("[redacted-jwt]", text)
    out = _API_TOKEN_PATTERN.sub("[redacted-api-token]", out)
    out = _BEARER_PATTERN.sub(r"\1[redacted]", out)
    out = _ENV_SECRET_PATTERN.sub(r"\1[redacted]", out)
    return out


def scrub_sensitive_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_secrets_in_text(value)
    if isinstance(value, dict):
        return scrub_sensitive_dict(value)
    if isinstance(value, list):
        return [scrub_sensitive_value(v) for v in value]
    return value


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "authorization",
        "jwt",
        "api_key",
        "auth_secret_key",
    }
)


def scrub_sensitive_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    out: dict[str, Any] = {}
    for k, v in data.items():
        lk = k.lower()
        if lk in _SENSITIVE_KEYS or "token" in lk or "secret" in lk or "password" in lk:
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = scrub_sensitive_dict(v) or {}
        elif isinstance(v, str):
            out[k] = mask_secrets_in_text(v)
        elif isinstance(v, list):
            out[k] = [scrub_sensitive_value(x) for x in v]
        else:
            out[k] = v
    return out
