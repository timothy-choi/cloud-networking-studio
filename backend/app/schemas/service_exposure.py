"""API models for service exposure (Step 40)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ServiceExposureCreate(BaseModel):
    """Optional TTL for an exposure row (hours)."""

    ttl_hours: int | None = Field(
        default=None,
        ge=1,
        le=720,
        description="When set, status becomes expired automatically after this many hours.",
    )


class ServiceExposureResponse(BaseModel):
    """One exposure record returned to clients."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    deployment_id: UUID
    runtime_resource_id: UUID
    exposure_type: str
    external_url: str | None = None
    external_host: str | None = None
    external_port: int | None = None
    status: str
    expires_at: datetime | None = None
    exposure_metadata: dict[str, Any] | None = Field(
        default=None,
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


class ServiceExposureListResponse(BaseModel):
    deployment_id: UUID
    exposures: list[ServiceExposureResponse]
