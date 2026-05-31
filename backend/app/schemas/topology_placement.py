"""API schemas for topology placement planning (Feature 59A)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlacementAssignedNode(BaseModel):
    node_id: str
    node_name: str
    replica_index: int
    display_name: str
    resource_cpu: float
    resource_memory_mb: int
    resource_disk_gb: float
    node_role: str
    exposure: str
    stateful: bool
    required_ports: list[int] = Field(default_factory=list)


class PlacementHost(BaseModel):
    host_index: int
    estimated_cpu_used: float
    estimated_memory_used_mb: int
    assigned_nodes: list[PlacementAssignedNode] = Field(default_factory=list)


class TopologyNodeResourceBreakdown(BaseModel):
    node_id: str
    node_name: str
    resource_cpu: float
    resource_memory_mb: int
    resource_disk_gb: float
    replicas: int
    node_role: str
    exposure: str
    stateful: bool


class TopologyResourceEstimateResponse(BaseModel):
    total_cpu: float
    total_memory_mb: int
    total_disk_gb: float
    total_replicas: int
    node_count: int
    workload_node_count: int
    placement_unit_count: int = 0
    nodes: list[TopologyNodeResourceBreakdown] = Field(default_factory=list)


class TopologyPlacementPlanResponse(BaseModel):
    total_cpu: float
    total_memory_mb: int
    total_disk_gb: float
    total_replicas: int
    node_count: int
    workload_node_count: int
    placement_unit_count: int
    provider: str
    recommended_host_count: int
    recommended_machine_type: str
    machine_rationale: str
    hosts: list[PlacementHost] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    exposed_ports: list[int] = Field(default_factory=list)
    suggested_template_id: str = "docker-vm"
    nodes: list[TopologyNodeResourceBreakdown] = Field(default_factory=list)


class GenerateInfrastructureDeploymentRequest(BaseModel):
    provider: str = "gcp"
    template_id: str = "docker-vm"
    machine_type: str | None = None
    host_count: int | None = Field(default=None, ge=1, le=10)
    variables: dict[str, Any] | None = None
    credentials_ref: str | None = None
    name: str | None = None


class GenerateInfrastructureDeploymentResponse(BaseModel):
    deployment: dict[str, Any]
    placement_plan: TopologyPlacementPlanResponse
    capacity_check: dict[str, Any]
