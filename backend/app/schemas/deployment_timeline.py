"""Deployment timeline API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deployment_id: UUID
    event_type: str
    status: str
    message: str
    request_id: str | None
    metadata: dict | None = Field(default=None, validation_alias="metadata_json")
    created_at: datetime


class DeploymentTimelineResponse(BaseModel):
    deployment_id: UUID
    events: list[TimelineEventRead]
