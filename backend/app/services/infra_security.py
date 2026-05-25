"""Security helpers for infrastructure deployments (Step 57C)."""

from __future__ import annotations

import re
from typing import Any

from app.core.secret_masking import scrub_sensitive_dict

_FORBIDDEN_VAR_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "private_key",
        "credentials",
        "aws_secret_access_key",
        "gcp_credentials_json",
    }
)

_SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$")
_PATH_TRAVERSAL = re.compile(r"\.\.|~|//")


def sanitize_variables(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Allow only safe scalar variables for template execution."""
    if not raw:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        key_str = str(key).strip()
        if not _SAFE_KEY_PATTERN.match(key_str):
            raise ValueError(f"Invalid variable key: {key_str}")
        lower = key_str.lower()
        if any(part in lower for part in _FORBIDDEN_VAR_KEYS):
            raise ValueError(f"Sensitive variable keys must use credentials_ref, not variables: {key_str}")
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and _PATH_TRAVERSAL.search(value):
                raise ValueError(f"Invalid path-like variable value for {key_str}")
            cleaned[key_str] = value
        else:
            raise ValueError(f"Variable {key_str} must be a scalar")
    return scrub_sensitive_dict(cleaned)


def validate_provider(provider: str, allowed: frozenset[str]) -> None:
    if provider not in allowed:
        raise ValueError(f"Unsupported provider '{provider}'. Allowed: {', '.join(sorted(allowed))}")


def redact_logs(text: str) -> str:
    from app.core.secret_masking import mask_secrets_in_text

    return mask_secrets_in_text(text) or ""
