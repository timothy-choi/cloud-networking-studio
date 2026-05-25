"""Pydantic schemas for runtime executor / runner observability."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RunnerOperationRecordResponse(BaseModel):
    operation: str
    provider: str
    status: str
    duration_ms: int
    request_id: str | None = None
    deployment_id: str | None = None
    topology_id: str | None = None
    error_message: str | None = None
    created_at: datetime | str


class RecentRunnerOperationsResponse(BaseModel):
    operations: list[RunnerOperationRecordResponse] = Field(default_factory=list)
    count: int = 0


class RunnerStatusDetailResponse(BaseModel):
    runner_reachable: bool
    runtime_executor: str
    runner_status: str | None = None
    status: str | None = None
    runtime_provider: str | None = None
    docker_reachable: bool | None = None
    kubernetes_reachable: bool | None = None
    current_context: str | None = None
    version: str | None = None
    git_sha: str | None = None
    build_time: str | None = None
    supported_operations: list[str] = Field(default_factory=list)
    last_runtime_error: str | None = None
    message: str | None = None
    checked_at: datetime | str
