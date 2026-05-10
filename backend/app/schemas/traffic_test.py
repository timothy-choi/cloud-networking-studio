"""Request/response schemas for traffic tests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.traffic_test import TrafficTestStatus, TrafficTestType


class PingTrafficTestRequest(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    count: int = Field(default=3, ge=1, le=10)


class HttpTrafficTestRequest(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    path: str = Field(default="/", max_length=512)
    port: int = Field(default=80, ge=1, le=65535)


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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    deployment_id: UUID | None
    source_node_id: UUID
    target_node_id: UUID | None
    test_type: TrafficTestType
    status: TrafficTestStatus
    command: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: TrafficTestResultResponse | None
