"""Project invitation API schemas (Step 54B)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

InvitationStatus = Literal["pending", "accepted", "declined", "expired", "revoked"]
InviteableRole = Literal["member", "viewer"]


class ProjectInvitationCreate(BaseModel):
    email: EmailStr
    role: InviteableRole = "member"


class ProjectInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    email: str
    role: str
    status: str
    invited_by_user_id: UUID
    accepted_by_user_id: UUID | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ProjectInvitationCreatedResponse(ProjectInvitationResponse):
    """Returned once from POST — includes accept token for email fallback (not stored)."""

    accept_token: str = Field(
        ...,
        description="One-time token for accept URL; also emailed to the invitee.",
    )


class InvitationActionResponse(BaseModel):
    status: str
    message: str
    project_id: UUID | None = None
