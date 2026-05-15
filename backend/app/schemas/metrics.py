"""Schemas for cross-topology observability (Step 32)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentEventLevel


class MetricsLatestEvent(BaseModel):
    """One row in the cross-deployment activity feed."""

    model_config = ConfigDict(from_attributes=False)

    id: UUID = Field(description="Deployment event row id.")
    source: Literal["deployment_event"] = Field(
        description="Origin of the row (extensible for future event tables)."
    )
    topology_id: UUID
    deployment_id: UUID
    level: DeploymentEventLevel
    message: str
    created_at: datetime


class MetricsSummaryResponse(BaseModel):
    """Aggregated counters for dashboards and operators."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_topologies": 3,
                "total_deployments": 5,
                "active_deployments": 1,
                "failed_deployments": 0,
                "total_traffic_tests": 12,
                "failed_traffic_tests": 1,
                "total_failure_injections": 4,
                "failed_failure_injections": 0,
                "latest_events": [
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440000",
                        "source": "deployment_event",
                        "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                        "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                        "level": "info",
                        "message": "Ensured Docker network cns-topology-550e8400",
                        "created_at": "2025-01-15T10:00:05Z",
                    }
                ],
            }
        }
    )

    total_topologies: int = Field(ge=0)
    total_deployments: int = Field(ge=0)
    active_deployments: int = Field(
        ge=0,
        description="Docker deployments in succeeded state (live workload), matching controller semantics.",
    )
    failed_deployments: int = Field(ge=0)
    total_traffic_tests: int = Field(ge=0)
    failed_traffic_tests: int = Field(ge=0)
    total_failure_injections: int = Field(ge=0)
    failed_failure_injections: int = Field(ge=0)
    latest_events: list[MetricsLatestEvent] = Field(
        default_factory=list,
        description="Recent deployment events across all topologies (newest first).",
    )
