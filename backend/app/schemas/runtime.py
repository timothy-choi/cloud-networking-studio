"""API schemas for runtime inspection and reconciliation."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentStatus


class RuntimeNetworkResponse(BaseModel):
    """Docker (or future) network observed at runtime."""

    model_config = ConfigDict(from_attributes=True)

    network_id: str
    name: str
    driver: str
    labels: dict[str, str] = Field(default_factory=dict)
    scope: str | None = None
    ipam_driver: str | None = None
    subnet_hints: list[str] = Field(default_factory=list)


class RuntimeNetworkInterfaceResponse(BaseModel):
    """One logical NIC attachment inside a container network namespace."""

    model_config = ConfigDict(from_attributes=True)

    docker_network: str = Field(description="Docker bridge network name (inspect key).")
    interface: str = Field(description="Synthetic interface name eth0, eth1, … by sort order.")
    ipv4: str
    gateway: str | None = None
    logical_network: str | None = Field(
        default=None,
        description="Logical network name from topology intent when labeled on the bridge.",
    )


class RuntimeContainerResponse(BaseModel):
    """Container bound to a topology node."""

    model_config = ConfigDict(from_attributes=True)

    container_id: str
    short_id: str
    name: str
    image: str
    status: str
    state_status: str | None = None
    running: bool
    labels: dict[str, str] = Field(default_factory=dict)
    node_id: UUID | None = None
    intended_ip: str | None = Field(
        default=None,
        description="Topology intent IP from node ip_address (design-time).",
    )
    actual_runtime_ip: str | None = Field(
        default=None,
        description="Primary IPv4 assigned by the runtime provider on the lab network.",
    )
    ipv4_by_network: dict[str, str] = Field(default_factory=dict)
    network_interfaces: list[RuntimeNetworkInterfaceResponse] = Field(
        default_factory=list,
        description="Per-bridge attachments with synthetic eth ordering.",
    )
    routes_lines: list[str] = Field(
        default_factory=list,
        description="IPv4 routing table from inside the container (best-effort exec).",
    )
    interface_lines: list[str] = Field(
        default_factory=list,
        description="IPv4 interface listing from inside the container (best-effort exec).",
    )
    ip_forward_enabled: bool | None = Field(
        default=None,
        description="Linux IPv4 forwarding flag read from /proc/sys/net/ipv4/ip_forward when available.",
    )
    forwarding_role: str | None = Field(
        default=None,
        description="segment_router vs leaf — from deploy-time labels for multinet labs.",
    )
    created: str | None = None
    started_at: str | None = None


class RuntimeTopologyResponse(BaseModel):
    """Aggregated runtime view for a topology."""

    topology_id: UUID
    status: str = Field(
        default="unknown",
        description=(
            "Coarse runtime view: not_deployed, destroyed, running, pending, failed, "
            "no_runtime_resources, out_of_sync, or degraded."
        ),
    )
    resources: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Persisted runtime access rows for the latest deployment (when present).",
    )
    warning: str | None = Field(
        default=None,
        description="Non-fatal drift or inspection issue (never implies HTTP 500).",
    )
    deployment_status: DeploymentStatus | None = None
    latest_deployment_id: UUID | None = None
    topology_sync_status: str | None = Field(
        default=None,
        description="in_sync or out_of_sync for the latest deployment.",
    )
    runtime_provider: str
    networks: list[RuntimeNetworkResponse]
    containers: list[RuntimeContainerResponse]
    node_runtime_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Maps topology node UUID string -> runtime container id.",
    )
    container_states: dict[str, str] = Field(
        default_factory=dict,
        description="Maps container id -> engine status string.",
    )


class RuntimeDeploymentResponse(BaseModel):
    """Runtime slice scoped to one deployment record."""

    deployment_id: UUID
    topology_id: UUID
    runtime_provider: str
    deployment_status: DeploymentStatus
    topology_sync_status: str | None = Field(
        default=None,
        description="Whether deployment config matches current topology.",
    )
    networks: list[RuntimeNetworkResponse]
    containers: list[RuntimeContainerResponse]
    node_runtime_mapping: dict[str, str] = Field(default_factory=dict)
    container_states: dict[str, str] = Field(default_factory=dict)
    # --- Runtime access layer (persisted from Go runner when available) ---
    status: str | None = Field(
        default=None,
        description="Coarse access status: running|pending|failed|destroyed (from deployment).",
    )
    namespace_or_network: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    endpoints: list[dict[str, Any]] = Field(default_factory=list)
    instructions: dict[str, Any] | None = None
    exposures: list[dict[str, Any]] = Field(
        default_factory=list,
        description="User-managed service exposure records (Step 40).",
    )


class RuntimeLogsResponse(BaseModel):
    """Recent stdout/stderr from the materialized node container."""

    node_id: UUID
    topology_id: UUID
    tail: int
    logs: str


class RuntimeStatsResponse(BaseModel):
    """Lightweight cgroup-style stats for a node container."""

    node_id: UUID
    topology_id: UUID
    cpu_percent: float | None = None
    memory_usage_bytes: int | None = None
    memory_limit_bytes: int | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None


class RuntimeLogsBundleResponse(BaseModel):
    """Deprecated: use ``RuntimeOperationsLogsResponse`` (Step 41 runtime operations)."""

    deployment_id: UUID
    logs_available: bool
    items: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeOperationsLogsResponse(BaseModel):
    """Aggregated or per-service runtime logs (runner or Python provider)."""

    deployment_id: UUID
    service_id: str | None = None
    logs: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)
    runtime_provider: str = "docker"


class RuntimeOperationsHealthResponse(BaseModel):
    status: str = Field(description="passed | failed | unsupported")
    target: str = ""
    latency_ms: int | None = None
    message: str = ""


class RuntimeOperationsTrafficRequest(BaseModel):
    source_runtime_resource_id: UUID
    target: str = Field(description="Runtime resource UUID, topology node UUID, hostname, or http(s) URL")
    protocol: Literal["http", "ping", "tcp", "dns", "command"] = "ping"
    port: int | None = Field(default=None, ge=1, le=65535)
    path: str | None = None
    command: list[str] | None = None


class RuntimeOperationsTrafficResponse(BaseModel):
    status: str
    source: str
    target: str
    protocol: str
    output: str = ""
    latency_ms: int | None = None


class RuntimeDeploymentSectionResponse(BaseModel):
    deployment_id: UUID
    nodes: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeDeploymentServicesSectionResponse(BaseModel):
    deployment_id: UUID
    services: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeInstructionsOnlyResponse(BaseModel):
    deployment_id: UUID
    instructions: dict[str, Any]


class StoppedContainerRef(BaseModel):
    """Reference to a container that exists but is not running."""

    container_id: str
    name: str


class ReconciliationResponse(BaseModel):
    """Drift detection output — remediation is not performed automatically."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                "missing_network": False,
                "missing_node_ids": [],
                "stopped_containers": [
                    {"container_id": "a1b2c3d4e5f6", "name": "cns-node-770e8400abc-demo-service"}
                ],
                "summary_lines": ["stopped=1 missing_nodes=0"],
            }
        }
    )

    deployment_id: UUID
    topology_id: UUID
    missing_network: bool = Field(description="True when the managed Docker network is absent.")
    missing_node_ids: list[UUID] = Field(description="Nodes without backing containers.")
    stopped_containers: list[StoppedContainerRef]
    summary_lines: list[str] = Field(description="Compact machine-oriented summaries for logs.")
