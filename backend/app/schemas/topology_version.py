"""Pydantic schemas for topology versions (Step 56)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TopologyVersionCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None


class TopologyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    version_number: int
    name: str | None
    description: str | None
    source: str
    parent_version_id: UUID | None
    created_by_user_id: UUID | None
    created_at: datetime


class TopologyVersionDetailResponse(TopologyVersionResponse):
    snapshot_json: dict = Field(description="Full topology snapshot at this version.")


class TopologyVersionListResponse(BaseModel):
    items: list[TopologyVersionResponse]


class TopologyVersionDiffResponse(BaseModel):
    base_version_id: UUID
    compare_version_id: UUID
    diff: dict


class TopologyVersionRollbackResponse(BaseModel):
    version: TopologyVersionResponse
    message: str = "Topology restored from snapshot. Deploy separately to apply runtime."
