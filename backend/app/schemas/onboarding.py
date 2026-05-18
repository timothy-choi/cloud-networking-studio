"""Onboarding and guided demo API schemas (Step 46)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingStepResponse(BaseModel):
    id: str
    title: str
    description: str
    completed: bool
    auto_detected: bool


class OnboardingStatusResponse(BaseModel):
    has_seen_onboarding: bool
    completed_steps: list[str] = Field(
        ...,
        description="Persisted step ids (manual completions plus auto-detections merged in). Sticky until POST /onboarding/reset.",
    )
    steps: list[OnboardingStepResponse]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OnboardingStatusUpdate(BaseModel):
    has_seen_onboarding: bool | None = None
    completed_steps: list[str] | None = Field(
        default=None,
        description="When set, replaces stored completions, then live auto-detection is merged in (empty list clears explicit history but project/topology may reappear from the workspace).",
    )


class OnboardingCompleteStepRequest(BaseModel):
    step: str = Field(..., min_length=1, max_length=64)


class StartDemoResponse(BaseModel):
    project_id: UUID
    topology_id: UUID
    deployment_id: UUID
    resumed: bool = Field(
        default=False,
        description="True when an existing active deployment was returned instead of a new deploy.",
    )
    detail: str | None = Field(
        default=None,
        description="Optional human-readable note (e.g. validation message surfaced as 400).",
    )
