"""Pydantic schemas for deployment APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentEventLevel, DeploymentStatus, TopologySyncStatus


class DeploymentEventResponse(BaseModel):
    """Single row from the deployment audit stream."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440000",
                "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                "level": "info",
                "message": "Ensured Docker network cns-topology-550e8400",
                "created_at": "2025-01-15T10:00:05Z",
            }
        },
    )

    id: UUID
    deployment_id: UUID
    level: DeploymentEventLevel = Field(description="Severity for UIs and filtering.")
    message: str = Field(description="Human-readable log line.")
    created_at: datetime


class DeploymentResponse(BaseModel):
    """Deployment aggregate returned by APIs."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "succeeded",
                "runtime_target": "docker",
                "started_at": "2025-01-15T10:00:00Z",
                "finished_at": "2025-01-15T10:00:12Z",
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-01-15T10:00:12Z",
                "events": [],
            }
        },
    )

    id: UUID
    topology_id: UUID
    status: DeploymentStatus = Field(description="Coarse deployment lifecycle state.")
    runtime_target: str = Field(description="Runtime key copied from the topology at deploy time.")
    topology_version_id: UUID | None = Field(
        default=None,
        description="Topology version snapshot used for this deployment.",
    )
    deployment_profile_id: UUID | None = Field(
        default=None,
        description="Deployment profile applied for env/runtime overrides.",
    )
    effective_config_json: dict | None = Field(
        default=None,
        description="Resolved config after profile overrides (secrets redacted in exports).",
    )
    topology_sync_status: TopologySyncStatus | None = Field(
        default=None,
        description="Whether this deployment still matches the topology definition.",
    )
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[DeploymentEventResponse] = Field(
        default_factory=list,
        description="Audit trail entries (newest deploy responses include embedded events).",
    )
