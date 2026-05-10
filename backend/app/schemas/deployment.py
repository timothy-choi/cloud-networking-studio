"""Pydantic schemas for deployment APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentEventLevel, DeploymentStatus


class DeploymentEventResponse(BaseModel):
    """Single row from the deployment audit stream."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deployment_id: UUID
    level: DeploymentEventLevel
    message: str
    created_at: datetime


class DeploymentResponse(BaseModel):
    """Deployment aggregate returned by APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    status: DeploymentStatus
    runtime_target: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[DeploymentEventResponse] = Field(default_factory=list)
