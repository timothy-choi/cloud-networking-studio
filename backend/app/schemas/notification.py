"""Notification API schemas (Step 54A)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID | None = None
    project_id: UUID | None = None
    type: str
    title: str
    message: str
    status: str
    severity: str
    metadata: dict | None = None
    created_at: datetime
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    unread_count: int = Field(ge=0)
