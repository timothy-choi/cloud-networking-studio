"""Request/response schemas for traffic tests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.traffic_test import TrafficTestStatus, TrafficTestType


class PingTrafficTestRequest(BaseModel):
    """ICMP ping between two deployed nodes (executed inside the source container)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_node_id": "770e8400-e29b-41d4-a716-446655440001",
                "target_node_id": "770e8400-e29b-41d4-a716-446655440002",
                "count": 3,
            }
        }
    )

    source_node_id: UUID = Field(description="Origin workload for the probe.")
    target_node_id: UUID = Field(description="Destination workload or address resolution target.")
    count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of ICMP echo requests to send.",
    )


class HttpTrafficTestRequest(BaseModel):
    """HTTP GET executed from the source container toward the target service."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_node_id": "770e8400-e29b-41d4-a716-446655440001",
                "target_node_id": "770e8400-e29b-41d4-a716-446655440002",
                "path": "/",
                "port": 80,
            }
        }
    )

    source_node_id: UUID
    target_node_id: UUID
    path: str = Field(default="/", max_length=512, description="HTTP path on the target.")
    port: int = Field(default=80, ge=1, le=65535, description="TCP port for the HTTP probe.")


class TrafficTestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    traffic_test_id: UUID
    exit_code: int
    stdout: str
    stderr: str
    latency_ms: float | None
    success: bool
    created_at: datetime


class TrafficTestResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "880e8400-e29b-41d4-a716-446655440000",
                "topology_id": "550e8400-e29b-41d4-a716-446655440000",
                "deployment_id": "550e8400-e29b-41d4-a716-446655440001",
                "source_node_id": "770e8400-e29b-41d4-a716-446655440001",
                "target_node_id": "770e8400-e29b-41d4-a716-446655440002",
                "test_type": "ping",
                "status": "succeeded",
                "command": "ping -c 3 172.18.0.2",
                "created_at": "2025-01-15T10:05:00Z",
                "started_at": "2025-01-15T10:05:01Z",
                "finished_at": "2025-01-15T10:05:03Z",
                "result": None,
            }
        },
    )

    id: UUID
    topology_id: UUID
    deployment_id: UUID | None = Field(
        default=None,
        description="Deployment context when known (may be null for older rows).",
    )
    source_node_id: UUID
    target_node_id: UUID | None
    test_type: TrafficTestType
    status: TrafficTestStatus
    command: str = Field(description="Shell command executed inside the source container.")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: TrafficTestResultResponse | None
