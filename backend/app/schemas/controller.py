"""Schemas for the manual runtime controller."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ControllerStatusResponse(BaseModel):
    controller_mode: str
    managed_deployments_count: int
    active_deployments_count: int
    supported_providers: list[str]
    last_run_timestamp: datetime | None = None
    health_summary: str


class ControllerRunOnceResponse(BaseModel):
    deployments_checked: int
    drift_detected: int = Field(
        ...,
        description="Number of deployments where any drift was observed.",
    )
    stopped_containers: int
    missing_containers: int
    missing_networks: int


class RestartedContainerRef(BaseModel):
    container_id: str
    name: str


class HealingResponse(BaseModel):
    deployment_id: UUID
    topology_id: UUID
    reconciliation_missing_network: bool
    reconciliation_missing_node_ids: list[UUID]
    reconciliation_stopped_count: int
    restarted_containers: list[RestartedContainerRef]
    skipped_missing_resources: list[str]
    healing_errors: list[str]
