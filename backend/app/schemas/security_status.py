"""Security status API schema (Step 53D)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SecurityStatusResponse(BaseModel):
    auth_secret_configured: bool
    auth_secret_strong: bool
    cors_strict: bool
    api_token_scopes_enabled: bool = True
    audit_logging_enabled: bool = True
    runtime_provider_access_configured: bool
    auth_require_login: bool
    environment: str
    warnings: list[str] = Field(default_factory=list)
