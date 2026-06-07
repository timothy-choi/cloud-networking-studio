"""Schemas for topology-aware infrastructure planning (Feature 58B)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CapacityStatus = Literal["compatible", "warning", "insufficient_capacity"]


class TopologyNodeResourceBreakdown(BaseModel):
    node_id: str
    name: str
    node_type: str
    cpu_request: float
    memory_request_mb: int
    disk_request_gb: float
    replicas: int
    resource_source: str = "default"


class TopologyResourceEstimateResponse(BaseModel):
    total_cpu: float
    total_memory_mb: int
    total_disk_gb: float
    total_replicas: int
    node_count: int
    workload_node_count: int
    nodes: list[TopologyNodeResourceBreakdown] = Field(default_factory=list)


class InfrastructureRecommendationsResponse(BaseModel):
    resource_estimate: TopologyResourceEstimateResponse
    recommendations: dict[str, list[str]]
    suggested_template_id: str
    suggested_provider: str
    suggested_variables: dict[str, Any] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)


class TopologyCapacityCheckResponse(BaseModel):
    status: CapacityStatus
    messages: list[str] = Field(default_factory=list)
    resource_estimate: TopologyResourceEstimateResponse
    selected_provider: str
    selected_machine_type: str | None = None
    available_memory_mb: int | None = None
    available_cpu: float | None = None
    required_memory_mb: int
    required_cpu: float


class GenerateInfrastructureDeploymentRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    provider: str = Field(default="gcp")
    template_id: str = Field(default="docker-vm")
    machine_type: str | None = Field(default=None, description="Override recommended machine type")
    credentials_ref: str | None = Field(default=None, max_length=255)
    variables: dict[str, Any] = Field(default_factory=dict)


class GenerateInfrastructureDeploymentResponse(BaseModel):
    deployment: dict[str, Any]
    resource_estimate: TopologyResourceEstimateResponse
    recommendations: dict[str, list[str]]
    capacity_check: TopologyCapacityCheckResponse
