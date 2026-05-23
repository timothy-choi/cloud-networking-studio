"""Quota usage schemas (Step 53B)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class QuotaLimits(BaseModel):
    max_active_deployments_per_project: int
    max_nodes_per_topology: int
    max_services_per_deployment: int
    max_terminal_sessions_per_user: int
    max_api_tokens_per_user: int


class QuotaUsage(BaseModel):
    active_deployments: int
    terminal_sessions: int
    api_tokens: int


class QuotaRemaining(BaseModel):
    active_deployments: int
    terminal_sessions: int
    api_tokens: int


class ProjectQuotaResponse(BaseModel):
    project_id: UUID
    limits: QuotaLimits
    usage: QuotaUsage
    remaining: QuotaRemaining
