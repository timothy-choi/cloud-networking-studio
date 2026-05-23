"""Platform security posture (Step 53D)."""

from __future__ import annotations

from app.core.config import settings
from app.core.security_validation import (
    cors_is_strict,
    cors_is_wildcard,
    is_weak_auth_secret,
)
from app.schemas.security_status import SecurityStatusResponse


def build_security_status() -> SecurityStatusResponse:
    warnings: list[str] = []
    secret_strong = not is_weak_auth_secret(settings.auth_secret_key)
    if not secret_strong:
        warnings.append("AUTH_SECRET_KEY is weak or still set to the development default.")
    cors_strict = cors_is_strict(settings.cors_origins, settings.cors_origin_regex)
    if cors_is_wildcard(settings.cors_origins):
        warnings.append("CNS_CORS_ORIGINS contains a wildcard origin.")
    if not settings.auth_require_login and settings.environment.lower() in ("production", "prod"):
        warnings.append("AUTH_REQUIRE_LOGIN is disabled in production.")

    runtime_ok = bool(
        (settings.runtime_executor or "").strip()
        or settings.go_runner_url
        or settings.database_url
    )

    return SecurityStatusResponse(
        auth_secret_configured=bool((settings.auth_secret_key or "").strip()),
        auth_secret_strong=secret_strong,
        cors_strict=cors_strict,
        api_token_scopes_enabled=True,
        audit_logging_enabled=True,
        runtime_provider_access_configured=runtime_ok,
        auth_require_login=settings.auth_require_login,
        environment=settings.environment,
        warnings=warnings,
    )
