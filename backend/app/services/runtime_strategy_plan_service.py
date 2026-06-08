"""Runtime strategy plan builder (Step 64)."""

from __future__ import annotations

from typing import Any

from app.models.topology import Topology
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services import topology_placement_persistence_service as placement_persist_svc
from app.services import topology_placement_planner_service as placement_svc
from app.services.runtime_strategy_registry import (
    RuntimeStrategy,
    assert_runtime_strategy_for_generation,
    get_runtime_strategy,
    require_runtime_strategy,
    runtime_strategy_to_dict,
)


def _host_count(plan: dict[str, Any]) -> int:
    hosts = plan.get("hosts") or []
    if hosts:
        return len(hosts)
    return int(plan.get("recommended_host_count") or plan.get("host_count") or 0)


def _requirement(key: str, label: str, description: str, *, required: bool = True) -> dict[str, Any]:
    return {"key": key, "label": label, "description": description, "required": required}


def _docker_vm_runtime_requirements() -> list[dict[str, Any]]:
    return [
        _requirement("runtime_targets", "Runtime targets", "1 remote_docker runtime target"),
        _requirement("docker", "Docker", "Docker engine installed on the remote host"),
        _requirement("docker_compose", "Docker Compose", "Docker Compose available on the remote host"),
        _requirement("ssh_credential", "SSH credential", "SSH credential profile for host access"),
        _requirement("remote_workdir", "remote_workdir", "Writable remote_workdir on the target host"),
    ]


def _docker_vm_deployment_requirements() -> list[dict[str, Any]]:
    return [
        _requirement("gcp_vm", "GCP VM", "Single GCP VM provisioned via Terraform apply"),
        _requirement("ssh_readiness", "SSH readiness", "SSH port 22 reachable and authenticated"),
        _requirement("ansible_configure", "Host configuration", "Ansible installs Docker and Compose on the VM"),
    ]


def _docker_multi_vm_runtime_requirements(*, host_count: int) -> list[dict[str, Any]]:
    return [
        _requirement("remote_hosts", "Remote hosts", f"{host_count} remote Docker-ready hosts"),
        _requirement("ssh_credentials", "SSH credentials", "Shared SSH credential or per-host credentials"),
        _requirement("host_placement", "Host placement mapping", "Placement plan host-to-node mapping"),
        _requirement("overlay_network", "Overlay networking", "Cross-host overlay/networking for multi-VM Compose"),
    ]


def _docker_multi_vm_deployment_requirements() -> list[dict[str, Any]]:
    return [
        _requirement(
            "multi_vm_apply",
            "Multi-VM apply",
            "Infrastructure apply for multiple VMs is not implemented yet",
            required=False,
        ),
    ]


def _k8s_runtime_requirements() -> list[dict[str, Any]]:
    return [
        _requirement("kubeconfig", "kubeconfig", "Valid kubeconfig for cluster API access"),
        _requirement("namespace", "Namespace", "Target Kubernetes namespace for workloads"),
        _requirement("image_registry", "Image registry", "Container image registry reachable from the cluster"),
        _requirement("ingress", "Ingress controller", "Ingress controller (optional for public exposure)", required=False),
    ]


def _k8s_deployment_requirements() -> list[dict[str, Any]]:
    return [
        _requirement(
            "k8s_provisioning",
            "Cluster provisioning",
            "Managed Kubernetes cluster provisioning is not implemented yet",
            required=False,
        ),
    ]


def _unsupported_features(strategy: RuntimeStrategy, *, host_count: int) -> list[str]:
    unsupported: list[str] = []
    if strategy.id == "docker-multi-vm":
        unsupported.extend(
            [
                "Multi-host infrastructure apply",
                "Runtime target generation for multiple hosts",
                "External deployment across multiple VMs",
                "Overlay networking automation",
            ]
        )
    elif strategy.id == "k8s-cluster":
        unsupported.extend(
            [
                "Kubernetes cluster provisioning",
                "Manifest or Helm deployment apply",
                "Runtime target generation for Kubernetes",
                "External deployment to Kubernetes",
            ]
        )
    elif strategy.host_model == "single_host" and host_count > 1:
        unsupported.append("Single-host runtime strategy cannot satisfy multi-host placement")
    return unsupported


def _capabilities(strategy: RuntimeStrategy) -> dict[str, bool]:
    return {
        "runtime_target_generation": strategy.supports_runtime_target_generation,
        "external_deployment": strategy.supports_external_deployment,
        "multi_host": strategy.supports_multi_host,
    }


def _generation_block_reason(strategy: RuntimeStrategy, *, host_count: int) -> str | None:
    try:
        assert_runtime_strategy_for_generation(strategy.id, host_count=host_count)
    except ValueError as exc:
        return str(exc)
    return None


def build_runtime_strategy_plan(
    *,
    placement_plan: dict[str, Any],
    strategy_recommendation: dict[str, Any],
    constraints: list[dict[str, Any]] | None = None,
    selected_strategy_id: str | None = None,
) -> dict[str, Any]:
    recommended = str(strategy_recommendation.get("recommended_strategy") or "docker-vm")
    selected = (selected_strategy_id or recommended).strip() or recommended
    strategy = require_runtime_strategy(selected)
    host_count = _host_count(placement_plan)
    constraints = constraints or []

    if strategy.id == "docker-vm":
        runtime_requirements = _docker_vm_runtime_requirements()
        deployment_requirements = _docker_vm_deployment_requirements()
    elif strategy.id == "docker-multi-vm":
        runtime_requirements = _docker_multi_vm_runtime_requirements(host_count=host_count or placement_plan.get("recommended_host_count") or 2)
        deployment_requirements = _docker_multi_vm_deployment_requirements()
    else:
        runtime_requirements = _k8s_runtime_requirements()
        deployment_requirements = _k8s_deployment_requirements()

    block_reason = _generation_block_reason(strategy, host_count=host_count)
    return {
        "recommended_runtime_strategy": recommended,
        "selected_runtime_strategy": selected,
        "runtime_strategy": runtime_strategy_to_dict(strategy),
        "capabilities": _capabilities(strategy),
        "runtime_target_requirements": runtime_requirements,
        "deployment_requirements": deployment_requirements,
        "unsupported_features": _unsupported_features(strategy, host_count=host_count),
        "can_generate_infrastructure": block_reason is None,
        "generation_block_reason": block_reason,
        "host_count": host_count,
        "placement_constraints_count": len(constraints),
    }


def build_runtime_strategy_plan_for_topology(
    topology: Topology,
    *,
    db,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    placement_mode: str = "first_fit",
    selected_strategy_id: str | None = None,
) -> dict[str, Any]:
    constraints = placement_persist_svc.constraints_as_dicts(db, topology.id)
    placement_plan = placement_svc.build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
    )
    strategy_recommendation = strategy_svc.build_strategy_recommendation(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
    )
    return build_runtime_strategy_plan(
        placement_plan=placement_plan,
        strategy_recommendation=strategy_recommendation,
        constraints=constraints,
        selected_strategy_id=selected_strategy_id,
    )


def runtime_strategy_summary_for_cost(
    *,
    strategy_id: str,
    host_count: int,
) -> dict[str, Any]:
    strategy = get_runtime_strategy(strategy_id) or require_runtime_strategy("docker-vm")
    return {
        "id": strategy.id,
        "display_name": strategy.display_name,
        "status": strategy.status,
        "runtime_provider": strategy.runtime_provider,
        "host_model": strategy.host_model,
        "deployment_model": strategy.deployment_model,
        "host_count": host_count,
    }
