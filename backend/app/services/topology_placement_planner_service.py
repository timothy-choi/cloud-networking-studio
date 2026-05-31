"""Generic topology placement planner (Feature 59A)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.topology import Topology
from app.services import credential_profile_service as profile_svc
from app.services.infra_apply_safety import GCP_APPLY_MACHINE_TYPES, GCP_APPLY_MAX_INSTANCES
from app.services.infra_security import sanitize_variables
from app.services.node_resource_metadata import (
    PlacementUnit,
    expand_placement_units,
    extract_node_resource_metadata,
)
from app.services.terraform_credentials_service import is_credential_profile_ref

_PROVIDER = "gcp"
_TEMPLATE_ID = "docker-vm"

_HOST_OVERHEAD_CPU = 0.25
_HOST_OVERHEAD_MEMORY_MB = 256


@dataclass(frozen=True)
class MachineSpec:
    machine_type: str
    vcpu: float
    memory_mb: int


_MACHINE_CATALOG: tuple[MachineSpec, ...] = (
    MachineSpec("e2-micro", 2, 1024),
    MachineSpec("e2-small", 2, 2048),
    MachineSpec("e2-medium", 2, 4096),
    MachineSpec("e2-standard-2", 2, 8192),
    MachineSpec("e2-standard-4", 4, 16384),
)


def _lookup_machine(machine_type: str | None) -> MachineSpec | None:
    key = (machine_type or "").strip()
    for spec in _MACHINE_CATALOG:
        if spec.machine_type == key:
            return spec
    return None


def _clamp_gcp_machine(machine_type: str) -> str:
    key = (machine_type or "").strip()
    if key in GCP_APPLY_MACHINE_TYPES:
        return key
    return "e2-medium"


def _pick_machine_type(total_cpu: float, total_memory_mb: int) -> tuple[str, str]:
    per_host_cpu = total_cpu + _HOST_OVERHEAD_CPU
    per_host_memory = total_memory_mb + _HOST_OVERHEAD_MEMORY_MB
    for spec in _MACHINE_CATALOG:
        if spec.vcpu >= per_host_cpu and spec.memory_mb >= per_host_memory:
            chosen = _clamp_gcp_machine(spec.machine_type)
            rationale = (
                f"Selected {chosen} ({spec.vcpu} vCPU, {spec.memory_mb} MB RAM) "
                f"to cover {total_cpu:.2f} vCPU and {total_memory_mb} MB workload demand "
                f"plus host overhead."
            )
            return chosen, rationale
    largest = _MACHINE_CATALOG[-1]
    chosen = _clamp_gcp_machine(largest.machine_type)
    return (
        chosen,
        f"Workload demand ({total_cpu:.2f} vCPU, {total_memory_mb} MB) exceeds catalog; "
        f"recommending largest apply-safe size {chosen}.",
    )


def _unit_sort_key(unit: PlacementUnit) -> tuple[float, int]:
    return (unit.resource_memory_mb, unit.resource_cpu)


def _host_capacity(spec: MachineSpec) -> tuple[float, int]:
    return (max(0.0, spec.vcpu - _HOST_OVERHEAD_CPU), max(0, spec.memory_mb - _HOST_OVERHEAD_MEMORY_MB))


def _bin_pack_units(
    units: list[PlacementUnit],
    spec: MachineSpec,
    *,
    max_hosts: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """First-fit decreasing bin pack by memory then CPU."""
    sorted_units = sorted(units, key=_unit_sort_key, reverse=True)
    host_cpu, host_memory = _host_capacity(spec)
    hosts: list[dict[str, Any]] = []
    limit = max_hosts if max_hosts is not None and max_hosts > 0 else None

    for unit in sorted_units:
        placed = False
        for host in hosts:
            if (
                host["estimated_cpu_used"] + unit.resource_cpu <= host_cpu
                and host["estimated_memory_used_mb"] + unit.resource_memory_mb
                <= host_memory
            ):
                host["estimated_cpu_used"] += unit.resource_cpu
                host["estimated_memory_used_mb"] += unit.resource_memory_mb
                host["assigned_nodes"].append(_assigned_node_payload(unit))
                placed = True
                break
        if placed:
            continue
        if limit is not None and len(hosts) >= limit:
            return hosts, False
        hosts.append(
            {
                "host_index": len(hosts),
                "estimated_cpu_used": unit.resource_cpu,
                "estimated_memory_used_mb": unit.resource_memory_mb,
                "assigned_nodes": [_assigned_node_payload(unit)],
            }
        )
    return hosts, True


def _assigned_node_payload(unit: PlacementUnit) -> dict[str, Any]:
    replica_suffix = f"#{unit.replica_index + 1}" if unit.replica_index > 0 else ""
    return {
        "node_id": unit.node_id,
        "node_name": unit.node_name,
        "replica_index": unit.replica_index,
        "display_name": f"{unit.node_name}{replica_suffix}",
        "resource_cpu": unit.resource_cpu,
        "resource_memory_mb": unit.resource_memory_mb,
        "resource_disk_gb": unit.resource_disk_gb,
        "node_role": unit.node_role,
        "exposure": unit.exposure,
        "stateful": unit.stateful,
        "required_ports": list(unit.required_ports),
    }


def _collect_warnings(
    *,
    units: list[PlacementUnit],
    hosts: list[dict[str, Any]],
    spec: MachineSpec,
    packed: bool,
    selected_machine_type: str | None,
    recommended_host_count: int,
) -> list[str]:
    warnings: list[str] = []
    host_cpu, host_memory = _host_capacity(spec)

    if not packed:
        warnings.append(
            f"Insufficient capacity: selected machine type cannot fit all placement units "
            f"within {len(hosts)} host(s) ({spec.machine_type}: {host_cpu:.2f} vCPU, "
            f"{host_memory} MB usable per host)."
        )

    for unit in units:
        if unit.exposure == "public":
            ports = ", ".join(str(p) for p in unit.required_ports) or "default app ports"
            warnings.append(
                f"Node '{unit.node_name}' has public exposure; ensure firewall allows ports: {ports}."
            )
        if unit.stateful:
            warnings.append(
                f"Node '{unit.node_name}' is stateful ({unit.resource_disk_gb:.1f} GB disk); "
                "persistent storage is not provisioned automatically by the docker-vm template."
            )
        if unit.placement_constraints:
            constraints = ", ".join(unit.placement_constraints)
            warnings.append(
                f"Node '{unit.node_name}' declares placement constraints ({constraints}) "
                "that are not enforced by the current planner."
            )

    if recommended_host_count > GCP_APPLY_MAX_INSTANCES:
        warnings.append(
            f"Placement recommends {recommended_host_count} hosts but GCP apply safety "
            f"limits vm_count to {GCP_APPLY_MAX_INSTANCES}; generated deployment will use "
            f"{GCP_APPLY_MAX_INSTANCES} VM(s)."
        )

    if selected_machine_type and selected_machine_type not in GCP_APPLY_MACHINE_TYPES:
        warnings.append(
            f"Machine type '{selected_machine_type}' is outside apply-safe sizes "
            f"({', '.join(sorted(GCP_APPLY_MACHINE_TYPES))}); clamped for deployment generation."
        )

    total_cpu = sum(u.resource_cpu for u in units)
    total_memory = sum(u.resource_memory_mb for u in units)
    if spec.vcpu < total_cpu + _HOST_OVERHEAD_CPU or spec.memory_mb < total_memory + _HOST_OVERHEAD_MEMORY_MB:
        if not any("Insufficient capacity" in w for w in warnings):
            warnings.append(
                f"Aggregate workload ({total_cpu:.2f} vCPU, {total_memory} MB) exceeds "
                f"single-host capacity for {spec.machine_type}."
            )

    return warnings


def build_resource_estimate(topology: Topology) -> dict[str, Any]:
    units = expand_placement_units(topology)
    nodes: list[dict[str, Any]] = []
    for node in topology.nodes or []:
        meta = extract_node_resource_metadata(node)
        if meta is None:
            continue
        nodes.append(
            {
                "node_id": str(node.id),
                "node_name": node.name,
                "resource_cpu": meta.resource_cpu,
                "resource_memory_mb": meta.resource_memory_mb,
                "resource_disk_gb": meta.resource_disk_gb,
                "replicas": meta.replicas,
                "node_role": meta.node_role,
                "exposure": meta.exposure,
                "stateful": meta.stateful,
            }
        )
    return {
        "total_cpu": round(sum(u.resource_cpu for u in units), 3),
        "total_memory_mb": sum(u.resource_memory_mb for u in units),
        "total_disk_gb": round(sum(u.resource_disk_gb for u in units), 2),
        "total_replicas": len(units),
        "node_count": len(topology.nodes or []),
        "workload_node_count": len(nodes),
        "placement_unit_count": len(units),
        "nodes": nodes,
    }


def build_placement_plan(
    topology: Topology,
    *,
    provider: str = _PROVIDER,
    machine_type: str | None = None,
    host_count: int | None = None,
) -> dict[str, Any]:
    provider_key = (provider or _PROVIDER).strip().lower()
    if provider_key != "gcp":
        raise ValueError("Placement planner currently supports provider=gcp only.")

    estimate = build_resource_estimate(topology)
    units = expand_placement_units(topology)
    if not units:
        return {
            **estimate,
            "provider": provider_key,
            "recommended_host_count": 0,
            "recommended_machine_type": "e2-micro",
            "machine_rationale": "No workload nodes with resource metadata; defaulting to e2-micro.",
            "hosts": [],
            "warnings": ["No placement units found; add resource metadata to topology nodes."],
            "exposed_ports": [],
            "suggested_template_id": _TEMPLATE_ID,
        }

    total_cpu = float(estimate["total_cpu"])
    total_memory_mb = int(estimate["total_memory_mb"])
    total_disk_gb = float(estimate["total_disk_gb"])

    if machine_type:
        spec = _lookup_machine(machine_type)
        if spec is None:
            raise ValueError(f"Unknown machine type '{machine_type}'.")
        chosen_machine = _clamp_gcp_machine(spec.machine_type)
        rationale = f"Using requested machine type {chosen_machine}."
    else:
        chosen_machine, rationale = _pick_machine_type(total_cpu, total_memory_mb)
        spec = _lookup_machine(chosen_machine)
        assert spec is not None

    hosts, packed = _bin_pack_units(units, spec, max_hosts=host_count)
    if not hosts:
        hosts, packed = _bin_pack_units(units, spec)

    recommended_host_count = len(hosts)
    warnings = _collect_warnings(
        units=units,
        hosts=hosts,
        spec=spec,
        packed=packed,
        selected_machine_type=machine_type,
        recommended_host_count=recommended_host_count,
    )

    exposed_ports = sorted(
        {
            port
            for unit in units
            if unit.exposure == "public"
            for port in (unit.required_ports or (80, 443))
        }
    )

    return {
        **estimate,
        "provider": provider_key,
        "recommended_host_count": recommended_host_count,
        "recommended_machine_type": chosen_machine,
        "machine_rationale": rationale,
        "hosts": hosts,
        "warnings": warnings,
        "exposed_ports": exposed_ports,
        "suggested_template_id": _TEMPLATE_ID,
        "total_cpu": total_cpu,
        "total_memory_mb": total_memory_mb,
        "total_disk_gb": total_disk_gb,
    }


def _default_deployment_variables(
    topology: Topology,
    plan: dict[str, Any],
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name_slug = re.sub(r"[^a-z0-9-]+", "-", topology.name.lower()).strip("-") or "cns-stack"
    if not name_slug.startswith("cns-"):
        name_slug = f"cns-{name_slug[:48]}"
    vm_count = min(
        max(1, int(plan.get("recommended_host_count") or 1)),
        GCP_APPLY_MAX_INSTANCES,
    )
    machine_type = _clamp_gcp_machine(str(plan.get("recommended_machine_type") or "e2-medium"))
    base: dict[str, Any] = {
        "project_id": "",
        "region": "us-central1",
        "zone": "us-central1-a",
        "machine_type": machine_type,
        "network_name": "default",
        "instance_name": name_slug[:62],
        "ssh_user": "ubuntu",
        "allowed_ssh_cidr": "203.0.113.0/24",
        "allowed_app_cidr": "203.0.113.0/24",
        "tags": "cns-docker-vm",
        "vm_count": vm_count,
        "deployment_name": topology.name,
    }
    if overrides:
        base.update(overrides)
    return sanitize_variables(base)


def build_generate_deployment_payload(
    topology: Topology,
    *,
    db: Session | None = None,
    provider: str = _PROVIDER,
    template_id: str = _TEMPLATE_ID,
    machine_type: str | None = None,
    host_count: int | None = None,
    variables: dict[str, Any] | None = None,
    credentials_ref: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    plan = build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
    )
    merged_vars = _default_deployment_variables(topology, plan, overrides=variables)
    cred_ref = (credentials_ref or "").strip() or None
    if plan["provider"] == "gcp" and cred_ref and is_credential_profile_ref(cred_ref):
        if db is None:
            raise ValueError("Database session required to resolve credential profile.")
        if not str(merged_vars.get("project_id") or "").strip():
            merged_vars["project_id"] = profile_svc.resolve_gcp_project_id_for_credentials_ref(
                db,
                credentials_ref=cred_ref,
                workspace_project_id=topology.project_id,
            )

    deployment_name = (name or f"{topology.name}-infra").strip()[:128]
    capacity_status = "compatible"
    if any("Insufficient capacity" in w for w in plan.get("warnings") or []):
        capacity_status = "insufficient_capacity"

    return {
        "name": deployment_name,
        "template_id": template_id,
        "provider": plan["provider"],
        "variables": merged_vars,
        "credentials_ref": cred_ref,
        "placement_plan": plan,
        "capacity_check": {
            "status": capacity_status,
            "messages": plan.get("warnings") or [],
            "resource_estimate": {
                k: plan[k]
                for k in (
                    "total_cpu",
                    "total_memory_mb",
                    "total_disk_gb",
                    "total_replicas",
                    "node_count",
                    "workload_node_count",
                    "nodes",
                )
                if k in plan
            },
            "selected_provider": plan["provider"],
            "selected_machine_type": merged_vars.get("machine_type"),
            "recommended_host_count": plan.get("recommended_host_count"),
        },
    }
