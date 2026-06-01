"""API schemas for deployment strategy recommendation (Feature 60)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StrategyStatus = Literal["available", "planning_only", "future"]


class DeploymentStrategyResponse(BaseModel):
    id: str
    display_name: str
    status: StrategyStatus
    description: str
    min_hosts: int
    max_hosts: int
    supports_multi_host: bool
    supports_stateful: bool
    supports_public_ingress: bool
    runtime_type: str
    template_id: str


class StrategyEvaluationSummary(BaseModel):
    host_count: int
    total_replicas: int
    cpu_utilization: float
    memory_utilization: float
    stateful_workloads: bool
    public_exposure: bool
    unsupported_constraints: bool
    placement_valid: bool


class StrategyRecommendationResponse(BaseModel):
    recommended_strategy: str
    alternatives: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    strategies: list[DeploymentStrategyResponse] = Field(default_factory=list)
    recommended_strategy_detail: DeploymentStrategyResponse | None = None
    evaluation: StrategyEvaluationSummary | None = None
