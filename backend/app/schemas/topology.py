"""Pydantic schemas for topology APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.topology import NodeType, TopologyStatus


class TopologyCreate(BaseModel):
    """Payload for creating a topology definition."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "edge-demo",
                "description": "Host + service on shared bridge",
                "runtime_target": "docker",
                "networking_mode": "docker_bridge",
                "status": "draft",
                "config": None,
            }
        }
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name shown in UIs and deployment events.",
    )
    description: str | None = Field(
        default=None,
        description="Optional longer description; not interpreted by the runtime provider.",
    )
    runtime_target: str = Field(
        ...,
        max_length=64,
        description="Runtime key (e.g. `docker`) used by `runtime_provider_for_topology`.",
    )
    networking_mode: str = Field(
        ...,
        max_length=64,
        description="How overlay/bridge networking should be interpreted when planning deploy.",
    )
    status: TopologyStatus | None = Field(
        default=None,
        description="Defaults to draft when omitted.",
    )
    config: dict[str, Any] | None = Field(
        default=None,
        description="Opaque JSON bag for future planner hints.",
    )


class TopologyResponse(BaseModel):
    """Topology row returned from the API."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "edge-demo",
                "description": "Host + service on shared bridge",
                "status": "draft",
                "runtime_target": "docker",
                "networking_mode": "docker_bridge",
                "config": None,
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-01-15T10:00:00Z",
            }
        },
    )

    id: UUID
    name: str
    description: str | None
    status: TopologyStatus
    runtime_target: str
    networking_mode: str
    config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class TopologyNodeCreate(BaseModel):
    """Payload for adding a node to a topology graph."""

    name: str = Field(..., min_length=1, max_length=255)
    node_type: NodeType
    image: str | None = Field(default=None, max_length=512)
    ip_address: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] | None = None


class TopologyNodeResponse(BaseModel):
    """Topology node returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    name: str
    node_type: NodeType
    image: str | None
    ip_address: str | None
    config: dict[str, Any] | None


class TopologyLinkCreate(BaseModel):
    """Payload for adding a link between two nodes in the same topology."""

    source_node_id: UUID
    target_node_id: UUID
    network_name: str = Field(..., max_length=255)
    cidr: str | None = Field(default=None, max_length=64)
    gateway: str | None = Field(default=None, max_length=64)
    vlan_tag: int | None = Field(default=None, ge=0, le=4094)
    source_endpoint_ip: str | None = Field(default=None, max_length=64)
    target_endpoint_ip: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] | None = None


class TopologyLinkResponse(BaseModel):
    """Topology link returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    network_name: str
    cidr: str | None
    gateway: str | None = None
    vlan_tag: int | None = None
    source_endpoint_ip: str | None = None
    target_endpoint_ip: str | None = None
    config: dict[str, Any] | None = None


class TopologyUpdate(BaseModel):
    """Partial update for topology metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TopologyStatus | None = None
    runtime_target: str | None = Field(default=None, max_length=64)
    networking_mode: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] | None = None


class TopologyNodeUpdate(BaseModel):
    """Partial update for a topology node (including merged config / UI positions)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    node_type: NodeType | None = None
    image: str | None = Field(default=None, max_length=512)
    ip_address: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] | None = None


class TopologyLinkUpdate(BaseModel):
    """Partial update for a topology link."""

    network_name: str | None = Field(default=None, max_length=255)
    cidr: str | None = Field(default=None, max_length=64)
    gateway: str | None = Field(default=None, max_length=64)
    vlan_tag: int | None = Field(default=None, ge=0, le=4094)
    source_endpoint_ip: str | None = Field(default=None, max_length=64)
    target_endpoint_ip: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] | None = None
