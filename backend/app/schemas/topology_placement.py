"""API schemas for topology placement planning (Feature 59A/59B)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field


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
    machine_type: str
    cpu_used: float
    cpu_capacity: float
    memory_used_mb: int
    memory_capacity_mb: int
    disk_used_gb: float = 0
    disk_capacity_gb: float = 30
    assigned_nodes: list[str] = Field(default_factory=list)
    assigned_node_details: list[PlacementAssignedNode] = Field(default_factory=list)
    estimated_cpu_used: float | None = None
    estimated_memory_used_mb: int | None = None
    utilization: dict[str, int] = Field(default_factory=dict)


class TopologyNodeResourceBreakdown(BaseModel):
    node_id: str
    node_name: str
    resource_cpu: float
    resource_memory_mb: int
    resource_disk_gb: float
    replicas: int
    node_role: str = "workload"
    exposure: str = "internal"
    stateful: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cpu(self) -> float:
        return self.resource_cpu

    @computed_field  # type: ignore[prop-decorator]
    @property
    def memory_mb(self) -> int:
        return self.resource_memory_mb

    @computed_field  # type: ignore[prop-decorator]
    @property
    def disk_gb(self) -> float:
        return self.resource_disk_gb


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
    id: str | None = None
    total_cpu: float
    total_memory_mb: int
    total_disk_gb: float
    total_replicas: int
    node_count: int
    workload_node_count: int
    placement_unit_count: int
    provider: str
    placement_mode: str = "first_fit"
    recommended_host_count: int
    host_count: int = 0
    recommended_machine_type: str
    machine_rationale: str
    hosts: list[PlacementHost] = Field(default_factory=list)
    placements: list[PlacementHost] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    exposed_ports: list[int] = Field(default_factory=list)
    suggested_template_id: str = "docker-vm"
    nodes: list[TopologyNodeResourceBreakdown] = Field(default_factory=list)
    constraints_used: list[dict[str, Any]] = Field(default_factory=list)


class PlacementConstraintCreate(BaseModel):
    constraint_type: str = Field(pattern="^(same_host|different_host|preferred_host)$")
    node_a: str = Field(min_length=1, max_length=255)
    node_b: str | None = Field(default=None, max_length=255)
    preferred_host: int | None = Field(default=None, ge=1, le=100)


class PlacementConstraintResponse(BaseModel):
    id: str
    topology_id: str
    constraint_type: str
    node_a: str
    node_b: str | None = None
    preferred_host: int | None = None
    created_at: Any


class PlacementConstraintListResponse(BaseModel):
    items: list[PlacementConstraintResponse] = Field(default_factory=list)


class GenerateInfrastructureDeploymentRequest(BaseModel):
    provider: str = "gcp"
    template_id: str = "docker-vm"
    machine_type: str | None = None
    host_count: int | None = Field(default=None, ge=1, le=10)
    placement_mode: str = Field(default="first_fit", pattern="^(first_fit|best_fit|balanced)$")
    variables: dict[str, Any] | None = None
    credentials_ref: str | None = None
    name: str | None = None


class GenerateInfrastructureDeploymentResponse(BaseModel):
    deployment: dict[str, Any]
    placement_plan: TopologyPlacementPlanResponse
    capacity_check: dict[str, Any]
