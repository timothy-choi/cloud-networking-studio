"""Audit log API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    status: str
    metadata: dict | None = Field(default=None, validation_alias="metadata_json")
    request_id: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
