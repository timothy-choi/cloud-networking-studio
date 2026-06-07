"""Deployment strategy recommendation engine (Feature 60)."""

from __future__ import annotations

from typing import Any

from app.models.topology import Topology
from app.services.deployment_strategy_registry import (
    DeploymentStrategy,
    get_strategy,
    list_strategies,
    strategy_to_dict,
)
from app.services import topology_placement_planner_service as placement_svc

_HIGH_REPLICA_THRESHOLD = 5
_CAPACITY_WARNING_PHRASES = (
    "Insufficient capacity",
    "exceed memory capacity",
    "exceed CPU capacity",
    "CPU demand exceeds",
    "exceed boot disk capacity",
)


def _has_unsupported_constraints(warnings: list[str]) -> bool:
    return any("not supported" in w.lower() for w in warnings)


def _has_capacity_issues(warnings: list[str]) -> bool:
    text = " ".join(warnings)
    return any(phrase in text for phrase in _CAPACITY_WARNING_PHRASES)


def _has_stateful_workloads(plan: dict[str, Any]) -> bool:
    for node in plan.get("nodes") or []:
        if node.get("stateful"):
            return True
    for host in plan.get("hosts") or []:
        for detail in host.get("assigned_node_details") or []:
            if detail.get("stateful"):
                return True
    return False


def _has_public_exposure(plan: dict[str, Any]) -> bool:
    if plan.get("exposed_ports"):
        return True
    for node in plan.get("nodes") or []:
        if node.get("exposure") == "public":
            return True
    return False


def _host_count(plan: dict[str, Any]) -> int:
    hosts = plan.get("hosts") or []
    if hosts:
        return len(hosts)
    return int(plan.get("recommended_host_count") or 0)


def _avg_cpu_utilization(plan: dict[str, Any]) -> float:
    hosts = plan.get("hosts") or []
    if not hosts:
        return 0.0
    ratios: list[float] = []
    for host in hosts:
        capacity = float(host.get("cpu_capacity") or 0)
        if capacity <= 0:
            continue
        ratios.append(float(host.get("cpu_used") or 0) / capacity)
    return sum(ratios) / len(ratios) if ratios else 0.0


def _avg_memory_utilization(plan: dict[str, Any]) -> float:
    hosts = plan.get("hosts") or []
    if not hosts:
        return 0.0
    ratios: list[float] = []
    for host in hosts:
        capacity = int(host.get("memory_capacity_mb") or 0)
        if capacity <= 0:
            continue
        ratios.append(int(host.get("memory_used_mb") or 0) / capacity)
    return sum(ratios) / len(ratios) if ratios else 0.0


def _placement_is_valid(plan: dict[str, Any]) -> bool:
    if not plan.get("placement_unit_count"):
        return False
    if _has_capacity_issues(plan.get("warnings") or []):
        return False
    return bool(plan.get("hosts"))


def recommend_strategy_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a placement plan and return strategy recommendation payload."""
    warnings: list[str] = list(plan.get("warnings") or [])
    reasons: list[str] = []
    alternatives: list[str] = []

    host_count = _host_count(plan)
    total_replicas = int(plan.get("total_replicas") or plan.get("placement_unit_count") or 0)
    unsupported_constraints = _has_unsupported_constraints(warnings)
    placement_valid = _placement_is_valid(plan)
    stateful = _has_stateful_workloads(plan)
    public_exposure = _has_public_exposure(plan)
    cpu_util = _avg_cpu_utilization(plan)
    mem_util = _avg_memory_utilization(plan)

    if host_count > 1:
        recommended = "docker-multi-vm"
        reasons.append(f"Placement spans {host_count} hosts")
        reasons.append("Multi-host Docker deployment is the closest supported strategy")
        alternatives.append("k8s-cluster")
    elif placement_valid and not unsupported_constraints:
        recommended = "docker-vm"
        reasons.append("Topology fits on a single host")
        reasons.append("No unsupported placement constraints detected")
        reasons.append("Remote Docker runtime is supported")
        if host_count == 1:
            reasons.append(
                f"Host utilization: {cpu_util * 100:.0f}% CPU, {mem_util * 100:.0f}% memory"
            )
        alternatives.append("docker-multi-vm")
        if total_replicas >= _HIGH_REPLICA_THRESHOLD:
            alternatives.append("k8s-cluster")
    elif not plan.get("placement_unit_count"):
        recommended = "docker-vm"
        reasons.append("Default single-host Docker VM strategy for empty or unconfigured topologies")
        warnings.append("Add resource metadata to topology nodes for an accurate placement plan.")
        alternatives.append("docker-multi-vm")
    else:
        recommended = "docker-vm"
        reasons.append("Single-host Docker VM is the only apply-ready strategy")
        if unsupported_constraints:
            reasons.append("Placement constraints detected; review warnings before deploying")
        if not placement_valid:
            reasons.append("Placement plan has capacity or packing issues")
        alternatives.append("docker-multi-vm")
        if total_replicas >= _HIGH_REPLICA_THRESHOLD:
            alternatives.append("k8s-cluster")

    if stateful:
        reasons.append("Stateful workloads detected; verify persistent storage requirements")
    if public_exposure:
        reasons.append("Public exposure detected; ingress and firewall rules may be required")

    if total_replicas >= _HIGH_REPLICA_THRESHOLD and "k8s-cluster" not in alternatives:
        alternatives.append("k8s-cluster")
        reasons.append(
            f"High replica count ({total_replicas}) may benefit from orchestration in the future"
        )

    # De-duplicate alternatives, exclude recommended, preserve registry order
    registry_order = [s.id for s in list_strategies()]
    seen: set[str] = {recommended}
    ordered_alternatives: list[str] = []
    for strategy_id in registry_order:
        if strategy_id in alternatives and strategy_id not in seen:
            ordered_alternatives.append(strategy_id)
            seen.add(strategy_id)

    strategy = get_strategy(recommended)
    strategy_entries = [strategy_to_dict(s) for s in list_strategies() if s.id in {recommended, *ordered_alternatives}]

    return {
        "recommended_strategy": recommended,
        "alternatives": ordered_alternatives,
        "reasons": reasons,
        "warnings": warnings,
        "strategies": strategy_entries,
        "recommended_strategy_detail": strategy_to_dict(strategy) if strategy else None,
        "evaluation": {
            "host_count": host_count,
            "total_replicas": total_replicas,
            "cpu_utilization": round(cpu_util, 3),
            "memory_utilization": round(mem_util, 3),
            "stateful_workloads": stateful,
            "public_exposure": public_exposure,
            "unsupported_constraints": unsupported_constraints,
            "placement_valid": placement_valid,
        },
    }


def build_strategy_recommendation(
    topology: Topology,
    *,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    placement_mode: str = "first_fit",
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plan = placement_svc.build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
    )
    recommendation = recommend_strategy_from_plan(plan)
    recommendation["placement_plan"] = plan
    plan["suggested_template_id"] = recommendation["recommended_strategy"]
    return recommendation


def resolve_template_id_for_strategy(strategy_id: str) -> str:
    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise ValueError(f"Unknown deployment strategy '{strategy_id}'.")
    return strategy.template_id
