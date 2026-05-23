"""Platform observability metrics schemas (Step 53C)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RuntimeProviderStatusMetrics(BaseModel):
    status: str
    runtime_executor: str
    runtime_provider: str | None = None
    runner_reachable: bool | None = None
    docker_reachable: bool | None = None
    kubernetes_reachable: bool | None = None
    message: str | None = None


class QuotaUsageMetrics(BaseModel):
    active_deployments: int
    terminal_sessions: int
    api_tokens: int
    limits: dict[str, int]


class ApiRequestMetrics(BaseModel):
    total_requests: int = Field(ge=0)
    by_status: dict[str, int] = Field(default_factory=dict)


class FailedOperationMetrics(BaseModel):
    action: str
    resource_type: str
    resource_id: str | None
    status: str
    message: str | None = None
    request_id: str | None = None
    created_at: datetime


class CleanupStatusMetrics(BaseModel):
    eligible_deployments: int = Field(ge=0)
    deployments_with_runtime_resources: int = Field(ge=0)
    stale_terminal_sessions: int = Field(ge=0)


class DeploymentDurationMetrics(BaseModel):
    average_deploy_duration_seconds: float | None = None
    sample_count: int = Field(ge=0, default=0)


class PlatformMetricsResponse(BaseModel):
    scope: str = "platform"
    active_deployments: int = Field(ge=0)
    deployment_success_count: int = Field(ge=0)
    deployment_failure_count: int = Field(ge=0)
    deploy_duration: DeploymentDurationMetrics
    active_terminal_sessions: int = Field(ge=0)
    runtime_provider_status: RuntimeProviderStatusMetrics
    quota_usage: QuotaUsageMetrics
    recent_failed_operations: list[FailedOperationMetrics] = Field(default_factory=list)
    cleanup_status: CleanupStatusMetrics
    api_requests: ApiRequestMetrics


class ProjectMetricsResponse(BaseModel):
    scope: str = "project"
    project_id: UUID
    active_deployments: int = Field(ge=0)
    deployment_success_count: int = Field(ge=0)
    deployment_failure_count: int = Field(ge=0)
    deploy_duration: DeploymentDurationMetrics
    active_terminal_sessions: int = Field(ge=0)
    quota_usage: QuotaUsageMetrics
    recent_failed_operations: list[FailedOperationMetrics] = Field(default_factory=list)
    cleanup_status: CleanupStatusMetrics


class DeploymentMetricsResponse(BaseModel):
    scope: str = "deployment"
    deployment_id: UUID
    topology_id: UUID
    project_id: UUID | None = None
    status: str
    deploy_duration_seconds: float | None = None
    runtime_resources_count: int = Field(ge=0)
    active_terminal_sessions: int = Field(ge=0)
    cleanup_status: CleanupStatusMetrics
    recent_failed_operations: list[FailedOperationMetrics] = Field(default_factory=list)
