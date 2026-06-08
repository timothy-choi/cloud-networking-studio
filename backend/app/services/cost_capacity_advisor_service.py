"""Provider-agnostic cost and capacity advisor (Step 62).

Uses static pricing tables for initial planning guidance. This service does not call live pricing APIs
and does not create, validate, or deploy infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MachinePrice:
    machine_type: str
    vcpu: float
    memory_mb: int
    monthly_low: float
    monthly_high: float


_DEFAULT_DISK_GB = 30.0
_DISK_MONTHLY_LOW_PER_GB = 0.03
_DISK_MONTHLY_HIGH_PER_GB = 0.04

_PRICING: dict[str, tuple[MachinePrice, ...]] = {
    "gcp": (
        MachinePrice("e2-micro", 2, 1024, 7, 11),
        MachinePrice("e2-small", 2, 2048, 13, 19),
        MachinePrice("e2-medium", 2, 4096, 25, 36),
    ),
    "aws": (
        MachinePrice("t3.micro", 2, 1024, 8, 12),
        MachinePrice("t3.small", 2, 2048, 15, 22),
        MachinePrice("t3.medium", 2, 4096, 30, 43),
    ),
}


def _provider_key(provider: str | None) -> str:
    return (provider or "gcp").strip().lower()


def _machine_catalog(provider: str) -> tuple[MachinePrice, ...]:
    return _PRICING.get(_provider_key(provider), ())


def _lookup_machine(provider: str, machine_type: str | None) -> MachinePrice | None:
    key = (machine_type or "").strip()
    for spec in _machine_catalog(provider):
        if spec.machine_type == key:
            return spec
    return None


def _percent(used: float, capacity: float) -> int:
    if capacity <= 0:
        return 0
    return max(0, round((used / capacity) * 100))


def _host_totals(plan: dict[str, Any]) -> dict[str, float]:
    hosts = plan.get("hosts") or []
    return {
        "cpu_used": sum(float(host.get("cpu_used") or host.get("estimated_cpu_used") or 0) for host in hosts),
        "cpu_capacity": sum(float(host.get("cpu_capacity") or 0) for host in hosts),
        "memory_used_mb": sum(float(host.get("memory_used_mb") or host.get("estimated_memory_used_mb") or 0) for host in hosts),
        "memory_capacity_mb": sum(float(host.get("memory_capacity_mb") or 0) for host in hosts),
        "disk_used_gb": sum(float(host.get("disk_used_gb") or 0) for host in hosts),
        "disk_capacity_gb": sum(float(host.get("disk_capacity_gb") or _DEFAULT_DISK_GB) for host in hosts),
    }


def estimate_monthly_cost(
    *,
    provider: str,
    machine_type: str,
    host_count: int,
    disk_allocation_gb: float,
) -> dict[str, Any]:
    provider_key = _provider_key(provider)
    spec = _lookup_machine(provider_key, machine_type)
    if spec is None:
        raise ValueError(f"Unsupported machine type '{machine_type}' for provider '{provider_key}'.")

    count = max(1, int(host_count or 1))
    disk_gb = max(0.0, float(disk_allocation_gb or 0))
    low = (spec.monthly_low * count) + (disk_gb * _DISK_MONTHLY_LOW_PER_GB)
    high = (spec.monthly_high * count) + (disk_gb * _DISK_MONTHLY_HIGH_PER_GB)
    return {
        "provider": provider_key,
        "machine_type": spec.machine_type,
        "host_count": count,
        "estimated_monthly_cost": {
            "low": round(low),
            "high": round(high),
            "currency": "USD",
        },
    }


def analyze_capacity(placement_plan: dict[str, Any]) -> dict[str, Any]:
    totals = _host_totals(placement_plan)
    return {
        "cpu_utilization_percent": _percent(totals["cpu_used"], totals["cpu_capacity"]),
        "memory_utilization_percent": _percent(totals["memory_used_mb"], totals["memory_capacity_mb"]),
        "disk_utilization_percent": _percent(totals["disk_used_gb"], totals["disk_capacity_gb"]),
    }


def analyze_headroom(placement_plan: dict[str, Any]) -> dict[str, Any]:
    totals = _host_totals(placement_plan)
    cpu_remaining = max(0.0, totals["cpu_capacity"] - totals["cpu_used"])
    memory_remaining = max(0.0, totals["memory_capacity_mb"] - totals["memory_used_mb"])
    disk_remaining = max(0.0, totals["disk_capacity_gb"] - totals["disk_used_gb"])
    return {
        "cpu_headroom_percent": max(0, 100 - _percent(totals["cpu_used"], totals["cpu_capacity"])),
        "memory_headroom_percent": max(0, 100 - _percent(totals["memory_used_mb"], totals["memory_capacity_mb"])),
        "disk_headroom_percent": max(0, 100 - _percent(totals["disk_used_gb"], totals["disk_capacity_gb"])),
        "remaining_cpu": round(cpu_remaining, 2),
        "remaining_memory_mb": int(round(memory_remaining)),
        "remaining_disk_gb": round(disk_remaining, 2),
    }


def assess_scaling_risk(capacity: dict[str, int]) -> dict[str, Any]:
    metrics = {
        "CPU": int(capacity.get("cpu_utilization_percent") or 0),
        "Memory": int(capacity.get("memory_utilization_percent") or 0),
        "Disk": int(capacity.get("disk_utilization_percent") or 0),
    }
    max_utilization = max(metrics.values() or [0])
    if max_utilization > 85:
        risk = "HIGH"
    elif max_utilization >= 70:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    reasons = [
        f"{label} utilization exceeds {percent}%"
        for label, percent in metrics.items()
        if percent >= 70
    ]
    return {"scaling_risk": risk, "reasons": reasons}


def _machine_fits(spec: MachinePrice, *, host_count: int, totals: dict[str, float]) -> bool:
    count = max(1, int(host_count or 1))
    cpu_capacity = spec.vcpu * count
    memory_capacity = spec.memory_mb * count
    return totals["cpu_used"] <= cpu_capacity and totals["memory_used_mb"] <= memory_capacity


def recommend_alternatives(
    *,
    provider: str,
    machine_type: str,
    host_count: int,
    placement_plan: dict[str, Any],
    scaling_risk: dict[str, Any],
) -> dict[str, str | None]:
    catalog = list(_machine_catalog(provider))
    current_index = next((idx for idx, spec in enumerate(catalog) if spec.machine_type == machine_type), -1)
    if current_index < 0:
        return {"cheaper_alternative": None, "safer_alternative": None}

    totals = _host_totals(placement_plan)
    cheaper = None
    for candidate in reversed(catalog[:current_index]):
        if _machine_fits(candidate, host_count=host_count, totals=totals):
            cheaper = candidate.machine_type
            break

    safer = None
    if scaling_risk.get("scaling_risk") in {"MEDIUM", "HIGH"}:
        for candidate in catalog[current_index + 1 :]:
            if _machine_fits(candidate, host_count=host_count, totals=totals):
                safer = candidate.machine_type
                break

    return {"cheaper_alternative": cheaper, "safer_alternative": safer}


def build_cost_capacity_analysis(
    placement_plan: dict[str, Any],
    *,
    provider: str | None = None,
    machine_type: str | None = None,
    host_count: int | None = None,
    runtime_strategy_id: str | None = None,
) -> dict[str, Any]:
    provider_key = _provider_key(provider or placement_plan.get("provider"))
    selected_machine_type = (machine_type or placement_plan.get("recommended_machine_type") or "").strip()
    selected_host_count = int(host_count or placement_plan.get("recommended_host_count") or len(placement_plan.get("hosts") or []) or 1)
    disk_allocation = sum(float(host.get("disk_capacity_gb") or _DEFAULT_DISK_GB) for host in (placement_plan.get("hosts") or []))
    if disk_allocation <= 0:
        disk_allocation = _DEFAULT_DISK_GB * selected_host_count

    capacity = analyze_capacity(placement_plan)
    headroom = analyze_headroom(placement_plan)
    scaling_risk = assess_scaling_risk(capacity)

    runtime_strategy = None
    if runtime_strategy_id:
        from app.services.runtime_strategy_plan_service import runtime_strategy_summary_for_cost

        runtime_strategy = runtime_strategy_summary_for_cost(
            strategy_id=runtime_strategy_id,
            host_count=selected_host_count,
        )

    return {
        "cost_estimate": estimate_monthly_cost(
            provider=provider_key,
            machine_type=selected_machine_type,
            host_count=selected_host_count,
            disk_allocation_gb=disk_allocation,
        ),
        "capacity": capacity,
        "headroom": headroom,
        "scaling_risk": scaling_risk,
        "alternatives": recommend_alternatives(
            provider=provider_key,
            machine_type=selected_machine_type,
            host_count=selected_host_count,
            placement_plan=placement_plan,
            scaling_risk=scaling_risk,
        ),
        "runtime_strategy": runtime_strategy,
    }
