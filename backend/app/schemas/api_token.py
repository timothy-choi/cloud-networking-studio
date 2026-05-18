"""Schemas for personal API tokens (Step 44)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class ApiTokenResponse(BaseModel):
    id: UUID
    name: str
    token_hint: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiTokenCreateResponse(ApiTokenResponse):
    """Returned once from ``POST /api-tokens`` with the plaintext secret."""

    token: str = Field(
        ...,
        description="Full bearer secret; store securely — not shown again.",
    )
