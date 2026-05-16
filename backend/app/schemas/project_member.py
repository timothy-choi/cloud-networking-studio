"""Project member API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


ProjectMemberRole = Literal["owner", "member", "viewer"]
InviteableRole = Literal["member", "viewer"]


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: str
    created_at: datetime


class ProjectMemberInvite(BaseModel):
    email: EmailStr
    role: InviteableRole = "member"


class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectMemberRole
