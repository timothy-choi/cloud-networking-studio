"""Deployment strategy registry (Feature 60)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StrategyStatus = Literal["available", "planning_only", "future"]


@dataclass(frozen=True)
class DeploymentStrategy:
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


_STRATEGIES: dict[str, DeploymentStrategy] = {
    "docker-vm": DeploymentStrategy(
        id="docker-vm",
        display_name="Docker VM",
        status="available",
        description="Single GCP VM with Docker for remote runtime deployment of arbitrary workloads.",
        min_hosts=1,
        max_hosts=1,
        supports_multi_host=False,
        supports_stateful=True,
        supports_public_ingress=True,
        runtime_type="docker",
        template_id="docker-vm",
    ),
    "docker-multi-vm": DeploymentStrategy(
        id="docker-multi-vm",
        display_name="Docker Multi-VM",
        status="planning_only",
        description="Multiple Docker-ready VMs for topologies that span more than one host.",
        min_hosts=2,
        max_hosts=10,
        supports_multi_host=True,
        supports_stateful=True,
        supports_public_ingress=True,
        runtime_type="docker",
        template_id="docker-multi-vm",
    ),
    "k8s-cluster": DeploymentStrategy(
        id="k8s-cluster",
        display_name="Kubernetes Cluster",
        status="future",
        description="Managed Kubernetes cluster for highly replicated or orchestrated workloads.",
        min_hosts=1,
        max_hosts=999,
        supports_multi_host=True,
        supports_stateful=True,
        supports_public_ingress=True,
        runtime_type="kubernetes",
        template_id="k8s-cluster",
    ),
}


def list_strategies() -> list[DeploymentStrategy]:
    return list(_STRATEGIES.values())


def get_strategy(strategy_id: str) -> DeploymentStrategy | None:
    return _STRATEGIES.get((strategy_id or "").strip())


def require_strategy(strategy_id: str) -> DeploymentStrategy:
    strategy = get_strategy(strategy_id)
    if strategy is None:
        known = ", ".join(sorted(_STRATEGIES))
        raise ValueError(f"Unknown deployment strategy '{strategy_id}'. Known strategies: {known}.")
    return strategy


def assert_strategy_available(strategy_id: str) -> DeploymentStrategy:
    strategy = require_strategy(strategy_id)
    if strategy.status == "planning_only":
        raise ValueError(
            f"Deployment strategy '{strategy.display_name}' ({strategy.id}) is planning-only and "
            "cannot be applied yet."
        )
    if strategy.status == "future":
        raise ValueError(
            f"Deployment strategy '{strategy.display_name}' ({strategy.id}) is not available yet."
        )
    return strategy


def strategy_to_dict(strategy: DeploymentStrategy) -> dict:
    return {
        "id": strategy.id,
        "display_name": strategy.display_name,
        "status": strategy.status,
        "description": strategy.description,
        "min_hosts": strategy.min_hosts,
        "max_hosts": strategy.max_hosts,
        "supports_multi_host": strategy.supports_multi_host,
        "supports_stateful": strategy.supports_stateful,
        "supports_public_ingress": strategy.supports_public_ingress,
        "runtime_type": strategy.runtime_type,
        "template_id": strategy.template_id,
    }
