"""Request/response schemas for failure injection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.failure_injection import (
    FailureInjectionFailureType,
    FailureInjectionStatus,
)


class FailureInjectionRequest(BaseModel):
    target_node_id: UUID
    description: str | None = Field(default=None, max_length=2000)


class FailureInjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    deployment_id: UUID | None
    target_node_id: UUID
    failure_type: FailureInjectionFailureType
    status: FailureInjectionStatus
    description: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_message: str | None
