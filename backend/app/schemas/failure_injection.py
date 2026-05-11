"""Request/response schemas for failure injection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.failure_injection import (
    FailureInjectionFailureType,
    FailureInjectionStatus,
)


class FailureInjectionRequest(BaseModel):
    """Target node for a disruptive operation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_node_id": "770e8400-e29b-41d4-a716-446655440002",
                "description": "Kill nginx mid-demo",
            }
        }
    )

    target_node_id: UUID = Field(description="Topology node whose backing container will be affected.")
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional operator note stored with the failure record.",
    )


class FailureInjectionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "990e8400-e29b-41d4-a716-446655440000",
                "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                "target_node_id": "770e8400-e29b-41d4-a716-446655440002",
                "failure_type": "kill_container",
                "status": "succeeded",
                "description": "Kill nginx mid-demo",
                "created_at": "2025-01-15T10:10:00Z",
                "started_at": "2025-01-15T10:10:01Z",
                "finished_at": "2025-01-15T10:10:02Z",
                "result_message": "signal delivered",
            }
        },
    )

    id: UUID
    topology_id: UUID
    deployment_id: UUID | None = Field(
        default=None,
        description="Latest deployment associated with the topology when the injection ran.",
    )
    target_node_id: UUID
    failure_type: FailureInjectionFailureType
    status: FailureInjectionStatus
    description: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_message: str | None = Field(
        default=None,
        description="Provider-specific outcome text suitable for dashboards.",
    )
