"""Runtime strategy registry (Step 64).

Maps deployment strategy recommendations to concrete runtime execution models,
capabilities, and requirements without implementing multi-host or Kubernetes apply yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StrategyStatus = Literal["available", "planning_only", "future"]
HostModel = Literal["single_host", "multi_host", "cluster"]


@dataclass(frozen=True)
class RuntimeStrategy:
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


_STRATEGIES: dict[str, RuntimeStrategy] = {
    "docker-vm": RuntimeStrategy(
        id="docker-vm",
        display_name="Docker VM",
        status="available",
        runtime_provider="remote_docker",
        host_model="single_host",
        deployment_model="docker_compose",
        supports_multi_host=False,
        supports_runtime_target_generation=True,
        supports_external_deployment=True,
        description="Single remote Docker host with SSH access for Compose-based workload deployment.",
    ),
    "docker-multi-vm": RuntimeStrategy(
        id="docker-multi-vm",
        display_name="Docker Multi-VM",
        status="planning_only",
        runtime_provider="remote_docker_cluster",
        host_model="multi_host",
        deployment_model="multi_host_compose",
        supports_multi_host=True,
        supports_runtime_target_generation=False,
        supports_external_deployment=False,
        description="Multiple Docker-ready VMs with host placement mapping; apply is not implemented yet.",
    ),
    "k8s-cluster": RuntimeStrategy(
        id="k8s-cluster",
        display_name="Kubernetes Cluster",
        status="future",
        runtime_provider="kubernetes",
        host_model="cluster",
        deployment_model="manifests_or_helm",
        supports_multi_host=True,
        supports_runtime_target_generation=False,
        supports_external_deployment=False,
        description="Managed Kubernetes cluster for orchestrated workloads; not available yet.",
    ),
}


def list_runtime_strategies() -> list[RuntimeStrategy]:
    return list(_STRATEGIES.values())


def get_runtime_strategy(strategy_id: str) -> RuntimeStrategy | None:
    return _STRATEGIES.get((strategy_id or "").strip())


def require_runtime_strategy(strategy_id: str) -> RuntimeStrategy:
    strategy = get_runtime_strategy(strategy_id)
    if strategy is None:
        known = ", ".join(sorted(_STRATEGIES))
        raise ValueError(f"Unknown runtime strategy '{strategy_id}'. Known strategies: {known}.")
    return strategy


def runtime_strategy_to_dict(strategy: RuntimeStrategy) -> dict:
    return {
        "id": strategy.id,
        "display_name": strategy.display_name,
        "status": strategy.status,
        "runtime_provider": strategy.runtime_provider,
        "host_model": strategy.host_model,
        "deployment_model": strategy.deployment_model,
        "supports_multi_host": strategy.supports_multi_host,
        "supports_runtime_target_generation": strategy.supports_runtime_target_generation,
        "supports_external_deployment": strategy.supports_external_deployment,
        "description": strategy.description,
    }


def assert_runtime_strategy_for_generation(strategy_id: str, *, host_count: int) -> RuntimeStrategy:
    """Validate that a runtime strategy can generate infrastructure for the given placement."""
    strategy = require_runtime_strategy(strategy_id)
    if strategy.status == "planning_only":
        raise ValueError(
            f"Runtime strategy '{strategy.display_name}' ({strategy.id}) is planning-only "
            "and cannot generate infrastructure yet."
        )
    if strategy.status == "future":
        raise ValueError(
            f"Runtime strategy '{strategy.display_name}' ({strategy.id}) is future "
            "and cannot generate infrastructure yet."
        )
    if not strategy.supports_runtime_target_generation:
        raise ValueError(
            f"Runtime strategy '{strategy.display_name}' ({strategy.id}) does not support "
            "runtime target generation yet."
        )
    if not strategy.supports_external_deployment:
        raise ValueError(
            f"Runtime strategy '{strategy.display_name}' ({strategy.id}) does not support "
            "external deployment yet."
        )
    if strategy.host_model == "single_host" and host_count != 1:
        raise ValueError(
            f"Runtime strategy '{strategy.id}' requires a single-host placement plan "
            f"(got {host_count} hosts)."
        )
    if strategy.host_model == "multi_host" and host_count < 2:
        raise ValueError(
            f"Runtime strategy '{strategy.id}' requires a multi-host placement plan "
            f"(got {host_count} hosts)."
        )
    return strategy
