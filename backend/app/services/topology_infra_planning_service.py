"""Topology-aware resource estimation and infrastructure recommendations (Feature 58B)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.topology import Topology, TopologyNode
from app.services.infra_apply_safety import GCP_APPLY_MACHINE_TYPES
from app.services.infra_security import sanitize_variables

_NETWORK_ONLY_TYPES = frozenset({"router", "switch"})
_RESOURCE_KEYS = ("cpu_request", "memory_request_mb", "disk_request_gb", "replicas")

_DEFAULT_CPU = 0.5
_DEFAULT_MEMORY_MB = 512
_DEFAULT_DISK_GB = 5.0
_DEFAULT_REPLICAS = 1

_IMAGE_HEURISTICS: tuple[tuple[re.Pattern[str], dict[str, float | int]], ...] = (
    (re.compile(r"postgres", re.I), {"cpu_request": 1.0, "memory_request_mb": 2048, "disk_request_gb": 20.0}),
    (re.compile(r"redis", re.I), {"cpu_request": 0.5, "memory_request_mb": 1024, "disk_request_gb": 8.0}),
    (re.compile(r"nginx", re.I), {"cpu_request": 0.25, "memory_request_mb": 256, "disk_request_gb": 5.0}),
    (re.compile(r"mysql|mariadb", re.I), {"cpu_request": 1.0, "memory_request_mb": 2048, "disk_request_gb": 25.0}),
    (re.compile(r"ubuntu", re.I), {"cpu_request": 0.5, "memory_request_mb": 1024, "disk_request_gb": 10.0}),
    (re.compile(r"alpine|busybox", re.I), {"cpu_request": 0.25, "memory_request_mb": 256, "disk_request_gb": 5.0}),
)

_NODE_TYPE_HEURISTICS: dict[str, dict[str, float | int]] = {
    "host": {"cpu_request": 0.5, "memory_request_mb": 512, "disk_request_gb": 8.0},
    "generic": {"cpu_request": 0.5, "memory_request_mb": 512, "disk_request_gb": 8.0},
    "gateway": {"cpu_request": 0.25, "memory_request_mb": 256, "disk_request_gb": 5.0},
    "router": {"cpu_request": 0.25, "memory_request_mb": 256, "disk_request_gb": 2.0},
    "switch": {"cpu_request": 0.1, "memory_request_mb": 128, "disk_request_gb": 1.0},
}


@dataclass(frozen=True)
class MachineSpec:
    machine_type: str
    vcpu: float
    memory_mb: int


_MACHINE_CATALOG: dict[str, tuple[MachineSpec, ...]] = {
    "gcp": (
        MachineSpec("e2-micro", 2, 1024),
        MachineSpec("e2-small", 2, 2048),
        MachineSpec("e2-medium", 2, 4096),
        MachineSpec("e2-standard-2", 2, 8192),
        MachineSpec("e2-standard-4", 4, 16384),
    ),
    "aws": (
        MachineSpec("t3.micro", 2, 1024),
        MachineSpec("t3.small", 2, 2048),
        MachineSpec("t3.medium", 2, 4096),
        MachineSpec("t3.large", 2, 8192),
        MachineSpec("t3.xlarge", 4, 16384),
    ),
    "azure": (
        MachineSpec("Standard_B1ms", 1, 2048),
        MachineSpec("Standard_B2s", 2, 4096),
        MachineSpec("Standard_B2ms", 2, 8192),
        MachineSpec("Standard_B4ms", 4, 16384),
    ),
}


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _infer_defaults(node: TopologyNode) -> dict[str, float | int]:
    image = (node.image or "").strip()
    for pattern, hints in _IMAGE_HEURISTICS:
        if pattern.search(image):
            return dict(hints)
    node_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
    return dict(_NODE_TYPE_HEURISTICS.get(node_type, _NODE_TYPE_HEURISTICS["host"]))


def _node_resource_requests(node: TopologyNode) -> dict[str, float | int]:
    cfg = node.config if isinstance(node.config, dict) else {}
    resources = cfg.get("resources") if isinstance(cfg.get("resources"), dict) else {}
    inferred = _infer_defaults(node)

    cpu = _coerce_float(
        cfg.get("cpu_request") or resources.get("cpu_request") or resources.get("cpu"),
        float(inferred["cpu_request"]),
    )
    memory = _coerce_int(
        cfg.get("memory_request_mb") or resources.get("memory_request_mb") or resources.get("memory_mb"),
        int(inferred["memory_request_mb"]),
    )
    disk = _coerce_float(
        cfg.get("disk_request_gb") or resources.get("disk_request_gb") or resources.get("disk_gb"),
        float(inferred["disk_request_gb"]),
    )
    replicas = _coerce_int(cfg.get("replicas") or resources.get("replicas"), _DEFAULT_REPLICAS)
    return {
        "cpu_request": max(0.1, cpu),
        "memory_request_mb": max(128, memory),
        "disk_request_gb": max(1.0, disk),
        "replicas": replicas,
    }


def _counts_as_workload(node: TopologyNode, resources: dict[str, float | int]) -> bool:
    node_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
    if node_type not in _NETWORK_ONLY_TYPES:
        return True
    cfg = node.config if isinstance(node.config, dict) else {}
    return any(key in cfg or (isinstance(cfg.get("resources"), dict) and key in cfg["resources"]) for key in _RESOURCE_KEYS)


def estimate_topology_resources(topology: Topology) -> dict[str, Any]:
    nodes = list(topology.nodes or [])
    breakdown: list[dict[str, Any]] = []
    total_cpu = 0.0
    total_memory_mb = 0
    total_disk_gb = 0.0
    total_replicas = 0
    workload_count = 0

    for node in nodes:
        resources = _node_resource_requests(node)
        if not _counts_as_workload(node, resources):
            continue
        workload_count += 1
        replicas = int(resources["replicas"])
        cpu = float(resources["cpu_request"])
        memory = int(resources["memory_request_mb"])
        disk = float(resources["disk_request_gb"])
        total_cpu += cpu * replicas
        total_memory_mb += memory * replicas
        total_disk_gb += disk * replicas
        total_replicas += replicas
        node_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
        breakdown.append(
            {
                "node_id": str(node.id),
                "name": node.name,
                "node_type": node_type,
                "cpu_request": cpu,
                "memory_request_mb": memory,
                "disk_request_gb": disk,
                "replicas": replicas,
            }
        )

    return {
        "total_cpu": round(total_cpu, 2),
        "total_memory_mb": int(total_memory_mb),
        "total_disk_gb": round(total_disk_gb, 2),
        "total_replicas": total_replicas,
        "node_count": len(nodes),
        "workload_node_count": workload_count,
        "nodes": breakdown,
    }


def _pick_machine_types(provider: str, estimate: dict[str, Any]) -> list[str]:
    catalog = _MACHINE_CATALOG.get(provider, ())
    required_cpu = float(estimate["total_cpu"])
    required_memory = int(estimate["total_memory_mb"])
    fitting = [
        spec.machine_type
        for spec in catalog
        if spec.memory_mb >= required_memory and spec.vcpu >= required_cpu
    ]
    if fitting:
        return fitting[:3]
    if catalog:
        return [catalog[-1].machine_type]
    return []


def _lookup_machine(provider: str, machine_type: str | None) -> MachineSpec | None:
    if not machine_type:
        return None
    for spec in _MACHINE_CATALOG.get(provider, ()):
        if spec.machine_type == machine_type:
            return spec
    return None


def _machine_type_key(provider: str) -> str:
    return "instance_type" if provider == "aws" else "machine_type"


def _clamp_gcp_apply_machine(machine_type: str) -> str:
    if machine_type in GCP_APPLY_MACHINE_TYPES:
        return machine_type
    for candidate in ("e2-medium", "e2-small", "e2-micro"):
        if candidate in GCP_APPLY_MACHINE_TYPES:
            return candidate
    return machine_type


def build_infrastructure_recommendations(topology: Topology) -> dict[str, Any]:
    estimate = estimate_topology_resources(topology)
    recommendations = {provider: _pick_machine_types(provider, estimate) for provider in _MACHINE_CATALOG}
    provider = "gcp"
    machine = recommendations["gcp"][0] if recommendations["gcp"] else "e2-medium"
    machine = _clamp_gcp_apply_machine(machine)
    suggested_variables = _default_deployment_variables(
        topology,
        estimate,
        provider=provider,
        machine_type=machine,
    )
    rationale = [
        f"{estimate['workload_node_count']} workload node(s) require ~{estimate['total_memory_mb']}MB RAM and {estimate['total_cpu']} vCPU.",
        f"Recommended GCP machine type: {machine} (docker-vm remote Docker host).",
    ]
    if estimate["total_replicas"] > 1:
        rationale.append(
            f"Topology declares {estimate['total_replicas']} total replicas — size the VM for consolidated workloads."
        )
    return {
        "resource_estimate": estimate,
        "recommendations": recommendations,
        "suggested_template_id": "docker-vm",
        "suggested_provider": provider,
        "suggested_variables": suggested_variables,
        "rationale": rationale,
    }


def _default_deployment_variables(
    topology: Topology,
    estimate: dict[str, Any],
    *,
    provider: str,
    machine_type: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name_slug = re.sub(r"[^a-z0-9-]+", "-", topology.name.lower()).strip("-") or "cns-stack"
    if not name_slug.startswith("cns-"):
        name_slug = f"cns-{name_slug[:48]}"
    vm_count = 1
    base: dict[str, Any] = {
        "region": "us-central1",
        "vm_count": vm_count,
        "deployment_name": topology.name,
    }
    if provider == "gcp":
        base.update(
            {
                "project_id": "",
                "zone": "us-central1-a",
                "machine_type": machine_type,
                "network_name": "default",
                "instance_name": name_slug[:62],
                "ssh_user": "ubuntu",
                "allowed_ssh_cidr": "203.0.113.0/24",
                "allowed_app_cidr": "203.0.113.0/24",
                "tags": "cns-docker-vm",
            }
        )
    elif provider == "aws":
        base.update(
            {
                "instance_type": machine_type,
                "allowed_ssh_cidr": "203.0.113.0/24",
                "allowed_app_cidr": "203.0.113.0/24",
                "tags": "cns-docker-vm",
            }
        )
    if overrides:
        base.update(overrides)
    return sanitize_variables(base)


def validate_topology_capacity(
    topology: Topology,
    *,
    provider: str,
    variables: dict[str, Any] | None,
) -> dict[str, Any]:
    estimate = estimate_topology_resources(topology)
    provider_key = provider.strip().lower()
    vars_json = variables or {}
    machine_key = _machine_type_key(provider_key)
    machine_type = str(vars_json.get(machine_key) or vars_json.get("machine_type") or "").strip() or None
    vm_count = max(1, int(vars_json.get("vm_count") or 1))

    spec = _lookup_machine(provider_key, machine_type)
    messages: list[str] = []
    status: str = "compatible"

    required_memory = int(estimate["total_memory_mb"])
    required_cpu = float(estimate["total_cpu"])

    if spec is None:
        if machine_type:
            status = "warning"
            messages.append(f"Unknown machine type '{machine_type}' for provider '{provider_key}' — capacity not verified.")
        return {
            "status": status,
            "messages": messages,
            "resource_estimate": estimate,
            "selected_provider": provider_key,
            "selected_machine_type": machine_type,
            "available_memory_mb": None,
            "available_cpu": None,
            "required_memory_mb": required_memory,
            "required_cpu": required_cpu,
        }

    available_memory = spec.memory_mb * vm_count
    available_cpu = spec.vcpu * vm_count

    if required_memory > available_memory:
        status = "insufficient_capacity"
        messages.append(
            f"Selected {machine_type} provides {available_memory}MB RAM but topology requires {required_memory}MB RAM."
        )
    elif required_memory > int(available_memory * 0.85):
        status = "warning"
        messages.append(
            f"Selected {machine_type} provides {available_memory}MB RAM; topology requires {required_memory}MB RAM (limited headroom)."
        )

    if required_cpu > available_cpu:
        if status != "insufficient_capacity":
            status = "insufficient_capacity"
        messages.append(
            f"Selected {machine_type} provides {available_cpu} vCPU but topology requires {required_cpu} vCPU."
        )
    elif required_cpu > available_cpu * 0.85 and status == "compatible":
        status = "warning"
        messages.append(
            f"Selected {machine_type} provides {available_cpu} vCPU; topology requires {required_cpu} vCPU (limited headroom)."
        )

    if (
        provider_key == "gcp"
        and machine_type
        and machine_type not in GCP_APPLY_MACHINE_TYPES
        and status == "compatible"
    ):
        status = "warning"
        messages.append(
            f"Selected {machine_type} exceeds current GCP apply safety allowlist; apply may be blocked until machine type is reduced."
        )

    return {
        "status": status,
        "messages": messages,
        "resource_estimate": estimate,
        "selected_provider": provider_key,
        "selected_machine_type": machine_type,
        "available_memory_mb": available_memory,
        "available_cpu": available_cpu,
        "required_memory_mb": required_memory,
        "required_cpu": required_cpu,
    }


def validate_deployment_capacity(deployment: InfrastructureDeployment, topology: Topology) -> dict[str, Any]:
    return validate_topology_capacity(
        topology,
        provider=deployment.provider,
        variables=deployment.variables_json,
    )


def build_generate_deployment_payload(
    topology: Topology,
    *,
    provider: str = "gcp",
    template_id: str = "docker-vm",
    machine_type: str | None = None,
    variables: dict[str, Any] | None = None,
    credentials_ref: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    planning = build_infrastructure_recommendations(topology)
    provider_key = provider.strip().lower()
    chosen_machine = machine_type
    if not chosen_machine:
        recs = planning["recommendations"].get(provider_key) or planning["recommendations"].get("gcp") or []
        chosen_machine = recs[0] if recs else "e2-medium"
    if provider_key == "gcp":
        chosen_machine = _clamp_gcp_apply_machine(chosen_machine)
    merged_vars = _default_deployment_variables(
        topology,
        planning["resource_estimate"],
        provider=provider_key,
        machine_type=chosen_machine,
        overrides=variables,
    )
    capacity = validate_topology_capacity(topology, provider=provider_key, variables=merged_vars)
    deployment_name = (name or f"{topology.name}-infra").strip()[:128]
    return {
        "name": deployment_name,
        "template_id": template_id,
        "provider": provider_key,
        "variables": merged_vars,
        "credentials_ref": credentials_ref,
        "resource_estimate": planning["resource_estimate"],
        "recommendations": planning["recommendations"],
        "capacity_check": capacity,
        "rationale": planning["rationale"],
    }
