"""Production security validation for secrets and CORS (Step 53D)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

_log = logging.getLogger("cns.security")

DEFAULT_DEV_AUTH_SECRET = "local-dev-only-change-AUTH_SECRET_KEY-in-production-min-32-chars"


def is_weak_auth_secret(secret: str) -> bool:
    s = (secret or "").strip()
    if len(s) < 32:
        return True
    if s == DEFAULT_DEV_AUTH_SECRET:
        return True
    lowered = s.lower()
    if "change-me" in lowered or "local-dev-only" in lowered:
        return True
    return False


def cors_is_wildcard(origins: str) -> bool:
    parts = [p.strip() for p in (origins or "").split(",") if p.strip()]
    return "*" in parts


def cors_is_localhost_only(origins: str) -> bool:
    parts = [p.strip().lower() for p in (origins or "").split(",") if p.strip()]
    if not parts:
        return True
    for origin in parts:
        if "localhost" not in origin and "127.0.0.1" not in origin:
            return False
    return True


def cors_is_strict(origins: str, origin_regex: str | None) -> bool:
    if cors_is_wildcard(origins):
        return False
    if not origins.strip():
        return False
    if origin_regex and origin_regex.strip() == ".*":
        return False
    return True


def validate_production_security(settings: Settings) -> tuple[list[str], list[str]]:
    """Return ``(warnings, errors)`` for startup checks."""
    warnings: list[str] = []
    errors: list[str] = []
    env = (settings.environment or "").strip().lower()
    is_prod = env in ("production", "prod")

    if is_weak_auth_secret(settings.auth_secret_key):
        msg = "AUTH_SECRET_KEY is weak or still set to the development default."
        if is_prod:
            errors.append(msg)
        else:
            warnings.append(msg)

    if cors_is_wildcard(settings.cors_origins):
        msg = "CNS_CORS_ORIGINS contains wildcard (*) — restrict origins in production."
        if is_prod:
            errors.append(msg)
        else:
            warnings.append(msg)

    if is_prod and cors_is_localhost_only(settings.cors_origins):
        warnings.append(
            "CNS_CORS_ORIGINS is localhost-only — set your public UI origin for production."
        )

    if is_prod and not settings.auth_require_login:
        warnings.append("AUTH_REQUIRE_LOGIN is false in production — enable login enforcement.")

    return warnings, errors


def run_startup_security_checks(settings: Settings) -> None:
    warnings, errors = validate_production_security(settings)
    for w in warnings:
        _log.warning("security check: %s", w)
    if errors:
        for e in errors:
            _log.error("security check: %s", e)
        raise RuntimeError(
            "Production security validation failed:\n- " + "\n- ".join(errors)
        )
