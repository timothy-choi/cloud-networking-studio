"""Schemas for safe runtime exec and restart (Step 42)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RuntimeExecRequestBody(BaseModel):
    command: str = Field(max_length=4000)
    timeout_seconds: int = Field(10, ge=1, le=120)


class RuntimeExecResultResponse(BaseModel):
    id: UUID
    deployment_id: UUID
    service_id: UUID | None = Field(
        default=None,
        description="Persisted runtime resource id (path ``service_id`` on exec routes).",
    )
    command: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    runtime_provider: str = ""
    message: str | None = None


class RuntimeExecResultListResponse(BaseModel):
    deployment_id: UUID
    items: list[RuntimeExecResultResponse]


class RuntimeRestartResponse(BaseModel):
    status: str
    message: str = ""
    runtime_provider: str = ""
