"""API schemas for runtime strategy planning (Step 64)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StrategyStatus = Literal["available", "planning_only", "future"]
HostModel = Literal["single_host", "multi_host", "cluster"]


class RuntimeStrategyResponse(BaseModel):
    id: str
    display_name: str
    status: StrategyStatus
    runtime_provider: str
    host_model: HostModel
    deployment_model: str
    supports_multi_host: bool
    supports_runtime_target_generation: bool
    supports_external_deployment: bool
    description: str


class RuntimeStrategyListResponse(BaseModel):
    items: list[RuntimeStrategyResponse] = Field(default_factory=list)


class RuntimeRequirementItem(BaseModel):
    key: str
    label: str
    description: str
    required: bool = True


class RuntimeStrategyCapabilities(BaseModel):
    runtime_target_generation: bool
    external_deployment: bool
    multi_host: bool


class RuntimeStrategyPlanResponse(BaseModel):
    recommended_runtime_strategy: str
    selected_runtime_strategy: str
    runtime_strategy: RuntimeStrategyResponse
    capabilities: RuntimeStrategyCapabilities
    runtime_target_requirements: list[RuntimeRequirementItem] = Field(default_factory=list)
    deployment_requirements: list[RuntimeRequirementItem] = Field(default_factory=list)
    unsupported_features: list[str] = Field(default_factory=list)
    can_generate_infrastructure: bool
    generation_block_reason: str | None = None
    host_count: int
    placement_constraints_count: int = 0
