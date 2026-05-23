"""Deployment cleanup schemas (Step 53B)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DeploymentCleanupStatusResponse(BaseModel):
    deployment_id: UUID
    status: str
    eligible_for_cleanup: bool
    reasons: list[str]
    runtime_resources_count: int
    stale_terminal_sessions: int
    expires_at: str | None = None
    expired: bool
    deployment_ttl_hours: int
    last_cleanup_at: str | None = None
    topology_id: UUID | None = None
    project_id: UUID | None = None


class DeploymentCleanupResponse(BaseModel):
    ok: bool
    deployment_id: UUID
    events: list[dict[str, str]]
