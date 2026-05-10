"""Pydantic schemas for topology APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.topology import NodeType, TopologyStatus


class TopologyCreate(BaseModel):
    """Payload for creating a topology definition."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    runtime_target: str = Field(..., max_length=64)
    networking_mode: str = Field(..., max_length=64)
    status: TopologyStatus | None = Field(
        default=None,
        description="Defaults to draft when omitted.",
    )
    config: dict[str, Any] | None = None


class TopologyResponse(BaseModel):
    """Topology row returned from the API."""

    model_config = ConfigDict(from_attributes=True)

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
    config: dict[str, Any] | None
