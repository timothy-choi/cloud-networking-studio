"""Schemas for the manual runtime controller."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControllerStatusResponse(BaseModel):
    """Snapshot of controller configuration and last reconcile/heal statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "controller_mode": "manual",
                "managed_deployments_count": 2,
                "active_deployments_count": 1,
                "supported_providers": ["docker"],
                "last_run_timestamp": "2025-01-15T10:15:00Z",
                "health_summary": "ok",
            }
        }
    )

    controller_mode: str = Field(description="Operating mode from settings / controller service.")
    managed_deployments_count: int
    active_deployments_count: int
    supported_providers: list[str] = Field(
        description="Runtime providers compiled into this binary.",
    )
    last_run_timestamp: datetime | None = None
    health_summary: str = Field(description="Compact human-readable summary for dashboards.")


class ControllerRunOnceResponse(BaseModel):
    """Aggregate counters after a single reconcile sweep."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "deployments_checked": 3,
                "drift_detected": 1,
                "stopped_containers": 1,
                "missing_containers": 0,
                "missing_networks": 0,
            }
        }
    )

    deployments_checked: int
    drift_detected: int = Field(
        ...,
        description="Number of deployments where any drift was observed.",
    )
    stopped_containers: int
    missing_containers: int
    missing_networks: int


class RestartedContainerRef(BaseModel):
    """Container that was restarted during a heal attempt."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "container_id": "a1b2c3d4e5f6",
                "name": "cns-node-770e8400abc-demo-service",
            }
        }
    )

    container_id: str = Field(description="Docker container id (may be truncated in UIs).")
    name: str = Field(description="Container name on the engine.")


class HealingResponse(BaseModel):
    """Structured outcome of a heal attempt including reconciliation context."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                "reconciliation_missing_network": False,
                "reconciliation_missing_node_ids": [],
                "reconciliation_stopped_count": 1,
                "restarted_containers": [
                    {"container_id": "a1b2c3d4e5f6", "name": "cns-node-770e8400abc-demo-service"}
                ],
                "skipped_missing_resources": [],
                "healing_errors": [],
            }
        }
    )

    deployment_id: UUID
    topology_id: UUID
    reconciliation_missing_network: bool = Field(
        description="Whether Docker reported the managed network absent.",
    )
    reconciliation_missing_node_ids: list[UUID] = Field(
        description="Nodes lacking containers at reconcile time.",
    )
    reconciliation_stopped_count: int
    restarted_containers: list[RestartedContainerRef] = Field(
        description="Containers the provider attempted to restart.",
    )
    skipped_missing_resources: list[str] = Field(
        description="Reasons healing could not proceed for some resources.",
    )
    healing_errors: list[str] = Field(
        description="Provider/SDK messages when healing failed partially.",
    )
