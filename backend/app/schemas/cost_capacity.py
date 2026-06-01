"""API schemas for cost and capacity analysis (Step 62)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EstimatedMonthlyCost(BaseModel):
    low: float
    high: float
    currency: str = "USD"


class CostEstimateResponse(BaseModel):
    provider: str
    machine_type: str
    host_count: int
    estimated_monthly_cost: EstimatedMonthlyCost


class CapacityAnalysisResponse(BaseModel):
    cpu_utilization_percent: int
    memory_utilization_percent: int
    disk_utilization_percent: int


class HeadroomAnalysisResponse(BaseModel):
    cpu_headroom_percent: int
    memory_headroom_percent: int
    disk_headroom_percent: int
    remaining_cpu: float
    remaining_memory_mb: int
    remaining_disk_gb: float


class ScalingRiskResponse(BaseModel):
    scaling_risk: str
    reasons: list[str] = Field(default_factory=list)


class CostCapacityAlternativesResponse(BaseModel):
    cheaper_alternative: str | None = None
    safer_alternative: str | None = None


class CostCapacityAnalysisResponse(BaseModel):
    cost_estimate: CostEstimateResponse
    capacity: CapacityAnalysisResponse
    headroom: HeadroomAnalysisResponse
    scaling_risk: ScalingRiskResponse
    alternatives: CostCapacityAlternativesResponse
