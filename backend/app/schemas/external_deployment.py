"""Pydantic schemas for external deployment records (Step 57B)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExternalDeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    topology_id: str
    target_id: str
    job_id: str | None
    compose_project_name: str
    remote_workdir: str
    status: str
    services_json: list[Any]
    metadata_json: dict[str, Any]
    created_at: datetime | str
    updated_at: datetime | str
    destroyed_at: datetime | str | None


class ExternalDeploymentListResponse(BaseModel):
    items: list[ExternalDeploymentResponse] = Field(default_factory=list)
