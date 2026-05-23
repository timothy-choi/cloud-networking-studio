"""Schemas for personal API tokens (Step 44, scopes Step 53D)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.api_token_scopes import ALL_API_TOKEN_SCOPES, SCOPE_LABELS


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] | None = Field(
        default=None,
        description="Optional scope list. Omit for full account access (legacy behavior).",
    )


class ApiTokenResponse(BaseModel):
    id: UUID
    name: str
    token_hint: str
    scopes: list[str] | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiTokenCreateResponse(ApiTokenResponse):
    """Returned once from ``POST /api-tokens`` with the plaintext secret."""

    token: str = Field(
        ...,
        description="Full bearer secret; store securely — not shown again.",
    )


class ApiTokenScopeInfo(BaseModel):
    scope: str
    label: str


def list_scope_catalog() -> list[ApiTokenScopeInfo]:
    return [
        ApiTokenScopeInfo(scope=s, label=SCOPE_LABELS.get(s, s))
        for s in sorted(ALL_API_TOKEN_SCOPES)
    ]
