"""Pydantic schemas for topology APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.topology import TopologyStatus


class TopologyCreate(BaseModel):
    """Payload for creating a topology definition."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    runtime_target: str = Field(..., max_length=64)
    networking_mode: str = Field(..., max_length=64)
    status: TopologyStatus | None = Field(
        default=None,
        description="Defaults to draft when omitted.",
    )
    config: dict[str, Any] | None = None


class TopologyResponse(BaseModel):
    """Topology row returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: TopologyStatus
    runtime_target: str
    networking_mode: str
    config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
