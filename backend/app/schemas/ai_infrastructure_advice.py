"""API schemas for AI infrastructure advisor (Feature 61)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AiInfrastructureAdviceRequest(BaseModel):
    provider: str = "gcp"
    selected_strategy: str | None = None
    selected_machine_type: str | None = None
    credential_profile_id: str | None = None


class RecommendedOverrides(BaseModel):
    machine_type: str | None = None
    strategy: str | None = None
    machine_type_valid: bool = False
    strategy_valid: bool = False


class AiInfrastructureAdviceResponse(BaseModel):
    summary: str
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    recommended_overrides: RecommendedOverrides = Field(default_factory=RecommendedOverrides)
    explanation: str
    advisor_mode: str = "heuristic"
    advisory_only: bool = True
