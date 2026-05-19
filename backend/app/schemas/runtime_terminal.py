"""Schemas for interactive runtime terminal sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TerminalSessionCreateResponse(BaseModel):
    session_id: UUID
    deployment_id: UUID
    service_id: UUID = Field(description="Persisted runtime service resource row id")
    status: str
    websocket_path: str
    expires_at: datetime
    max_duration_seconds: int
    idle_timeout_seconds: int
    runtime_provider: str
    message: str | None = None


class TerminalSessionCloseResponse(BaseModel):
    session_id: UUID
    status: str
    close_reason: str | None = None
