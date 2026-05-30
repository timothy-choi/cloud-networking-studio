"""Pydantic schemas for external deployment jobs (Step 57A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


JOB_MODES = frozenset({"validate", "plan", "apply", "destroy"})
JOB_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})


def enabled_job_modes_for_target_type(target_type: str) -> frozenset[str]:
    from app.services.external_deployment_job_service import enabled_modes_for_target

    return enabled_modes_for_target(target_type)


class ExternalDeploymentJobCreate(BaseModel):
    target_id: str
    mode: str = Field(pattern="^(validate|plan|apply|destroy)$")


class ExternalDeploymentJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    topology_id: str
    target_id: str
    mode: str
    status: str
    logs: str | None
    artifact_refs: list[Any]
    created_by_user_id: str | None
    created_at: datetime | str
    started_at: datetime | str | None
    finished_at: datetime | str | None


class ExternalDeploymentJobListResponse(BaseModel):
    items: list[ExternalDeploymentJobResponse] = Field(default_factory=list)


class ExternalDeploymentJobLogsResponse(BaseModel):
    job_id: str
    status: str
    logs: str
