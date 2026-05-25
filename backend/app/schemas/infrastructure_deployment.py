"""Pydantic schemas for infrastructure deployments (Step 57C)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

INFRA_DEPLOYMENT_STATUSES = frozenset(
    {
        "pending",
        "validating",
        "planning",
        "awaiting_confirmation",
        "applying",
        "configuring",
        "succeeded",
        "failed",
        "destroying",
        "destroyed",
    }
)

SUPPORTED_PROVIDERS = frozenset({"local", "mock", "gcp", "aws"})
SUPPORTED_TEMPLATES = frozenset({"local-mock", "gcp-vm", "aws-ec2", "docker-vm"})


class InfrastructureDeploymentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    template_id: str
    provider: str = "local"
    variables: dict[str, Any] = Field(default_factory=dict)


class InfrastructureDeploymentResponse(BaseModel):
    id: str
    project_id: str
    topology_id: str
    name: str
    stack_type: str
    template_id: str
    provider: str
    status: str
    variables_json: dict[str, Any]
    plan_summary_json: dict[str, Any] | None
    outputs_json: dict[str, Any]
    inventory_json: dict[str, Any]
    state_metadata_json: dict[str, Any]
    events_json: list[dict[str, Any]]
    metrics_json: dict[str, Any]
    runtime_targets_json: list[dict[str, Any]]
    error_message: str | None
    confirmed_at: datetime | None
    confirmed_by_user_id: str | None
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
    destroyed_at: datetime | None

    model_config = {"from_attributes": True}


class InfrastructureDeploymentListResponse(BaseModel):
    items: list[InfrastructureDeploymentResponse]


class InfrastructureExecutionResponse(BaseModel):
    id: str
    infrastructure_deployment_id: str
    execution_type: str
    mode: str
    status: str
    runner_execution_id: str | None
    logs: str | None
    artifact_refs: list[dict[str, Any]]
    duration_ms: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class InfrastructureExecutionListResponse(BaseModel):
    items: list[InfrastructureExecutionResponse]


class InfrastructureTemplateInfo(BaseModel):
    template_id: str
    provider: str
    description: str
    supported_providers: list[str]


class InfrastructureTemplateListResponse(BaseModel):
    items: list[InfrastructureTemplateInfo]


class InfrastructureDeploymentConfirmRequest(BaseModel):
    """User approval gate before terraform apply."""

    confirm: bool = True
