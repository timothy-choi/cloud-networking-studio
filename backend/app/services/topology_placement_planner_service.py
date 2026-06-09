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
_PLACEMENT_MODES = frozenset({"first_fit", "best_fit", "balanced"})

_HOST_OVERHEAD_CPU = 0.25
_HOST_OVERHEAD_MEMORY_MB = 256
_HOST_BOOT_DISK_GB = 30.0


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


def _unit_matches(ref: str | None, unit: PlacementUnit) -> bool:
    key = str(ref or "").strip()
    return bool(key) and key in {unit.node_id, unit.node_name}


def _host_units(host: dict[str, Any]) -> list[dict[str, Any]]:
    return list(host.get("_node_details") or host.get("assigned_node_details") or [])


def _host_has_ref(host: dict[str, Any], ref: str | None) -> bool:
    key = str(ref or "").strip()
    if not key:
        return False
    for detail in _host_units(host):
        if key in {str(detail.get("node_id") or ""), str(detail.get("node_name") or "")}:
            return True
    return False


def _constraints_for_unit(unit: PlacementUnit, constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        c
        for c in constraints
        if _unit_matches(c.get("node_a"), unit) or _unit_matches(c.get("node_b"), unit)
    ]


def _constraint_peer_ref(unit: PlacementUnit, constraint: dict[str, Any]) -> str | None:
    if _unit_matches(constraint.get("node_a"), unit):
        return constraint.get("node_b")
    if _unit_matches(constraint.get("node_b"), unit):
        return constraint.get("node_a")
    return None


def _can_place_on_host(
    unit: PlacementUnit,
    host: dict[str, Any],
    spec: MachineSpec,
    constraints: list[dict[str, Any]],
) -> bool:
    if (
        float(host.get("_cpu_used") or 0) + unit.resource_cpu > spec.vcpu
        or int(host.get("_memory_used_mb") or 0) + unit.resource_memory_mb > spec.memory_mb
        or float(host.get("_disk_used_gb") or 0) + unit.resource_disk_gb > _HOST_BOOT_DISK_GB
    ):
        return False
    for constraint in _constraints_for_unit(unit, constraints):
        ctype = constraint.get("constraint_type")
        peer = _constraint_peer_ref(unit, constraint)
        if ctype == "different_host" and _host_has_ref(host, peer):
            return False
        if ctype == "same_host":
            peer_is_placed = any(_host_has_ref(existing, peer) for existing in constraint.get("_hosts", []))
            if peer_is_placed and not _host_has_ref(host, peer):
                return False
    return True


def _append_unit_to_host(host: dict[str, Any], unit: PlacementUnit) -> None:
    host["_cpu_used"] = float(host.get("_cpu_used") or 0) + unit.resource_cpu
    host["_memory_used_mb"] = int(host.get("_memory_used_mb") or 0) + unit.resource_memory_mb
    host["_disk_used_gb"] = float(host.get("_disk_used_gb") or 0) + unit.resource_disk_gb
    host.setdefault("_node_details", []).append(_assigned_node_payload(unit))


def _candidate_hosts(
    unit: PlacementUnit,
    hosts: list[dict[str, Any]],
    spec: MachineSpec,
    placement_mode: str,
    constraints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [host for host in hosts if _can_place_on_host(unit, host, spec, constraints)]
    preferred = [
        c
        for c in _constraints_for_unit(unit, constraints)
        if c.get("constraint_type") == "preferred_host" and c.get("preferred_host")
    ]
    if preferred:
        indexes = {int(c["preferred_host"]) for c in preferred}
        preferred_candidates = [
            host for idx, host in enumerate(hosts, start=1) if idx in indexes and host in candidates
        ]
        if preferred_candidates:
            return preferred_candidates

    if placement_mode == "best_fit":
        return sorted(
            candidates,
            key=lambda host: (
                (spec.memory_mb - (int(host.get("_memory_used_mb") or 0) + unit.resource_memory_mb)),
                (spec.vcpu - (float(host.get("_cpu_used") or 0) + unit.resource_cpu)),
            ),
        )
    if placement_mode == "balanced":
        return sorted(
            candidates,
            key=lambda host: (
                (float(host.get("_cpu_used") or 0) / max(0.01, spec.vcpu))
                + (int(host.get("_memory_used_mb") or 0) / max(1, spec.memory_mb))
                + (float(host.get("_disk_used_gb") or 0) / max(0.01, _HOST_BOOT_DISK_GB))
            ),
        )
    return candidates


def _bin_pack_units(
    units: list[PlacementUnit],
    spec: MachineSpec,
    *,
    max_hosts: int | None = None,
    placement_mode: str = "first_fit",
    constraints: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Pack units by selected placement mode."""
    sorted_units = sorted(units, key=_unit_sort_key, reverse=True)
    hosts: list[dict[str, Any]] = []
    limit = max_hosts if max_hosts is not None and max_hosts > 0 else None
    normalized_mode = placement_mode if placement_mode in _PLACEMENT_MODES else "first_fit"
    constraint_list = [dict(c) for c in (constraints or [])]
    if normalized_mode == "balanced" and limit:
        hosts = [{"_cpu_used": 0.0, "_memory_used_mb": 0, "_disk_used_gb": 0.0, "_node_details": []} for _ in range(limit)]

    for unit in sorted_units:
        for constraint in constraint_list:
            constraint["_hosts"] = hosts
        candidates = _candidate_hosts(unit, hosts, spec, normalized_mode, constraint_list)
        if candidates:
            _append_unit_to_host(candidates[0], unit)
            continue
        if limit is not None and len(hosts) >= limit:
            return [_finalize_host(host, spec) for host in hosts], False
        next_host = {"_cpu_used": 0.0, "_memory_used_mb": 0, "_disk_used_gb": 0.0, "_node_details": []}
        if not _can_place_on_host(unit, next_host, spec, constraint_list):
            _append_unit_to_host(next_host, unit)
            hosts.append(next_host)
            return [_finalize_host(host, spec) for host in hosts], False
        _append_unit_to_host(next_host, unit)
        hosts.append(next_host)
    return [_finalize_host(host, spec) for host in hosts], True


def _finalize_host(raw: dict[str, Any], spec: MachineSpec) -> dict[str, Any]:
    details = raw.get("_node_details") or []
    disk_used = round(float(raw.get("_disk_used_gb") or 0), 2)
    cpu_used = round(float(raw.get("_cpu_used") or 0), 3)
    memory_used = int(raw.get("_memory_used_mb") or 0)
    return {
        "host_index": 0,  # assigned after packing
        "machine_type": spec.machine_type,
        "cpu_used": cpu_used,
        "cpu_capacity": float(spec.vcpu),
        "memory_used_mb": memory_used,
        "memory_capacity_mb": int(spec.memory_mb),
        "disk_used_gb": disk_used,
        "disk_capacity_gb": _HOST_BOOT_DISK_GB,
        "utilization": {
            "cpu_utilization": round(cpu_used / max(0.01, float(spec.vcpu)) * 100),
            "memory_utilization": round(memory_used / max(1, int(spec.memory_mb)) * 100),
            "disk_utilization": round(disk_used / max(0.01, _HOST_BOOT_DISK_GB) * 100),
        },
        "assigned_nodes": [str(node["display_name"]) for node in details],
        "assigned_node_details": details,
        # Backward-compatible aliases
        "estimated_cpu_used": round(float(raw.get("_cpu_used") or 0), 3),
        "estimated_memory_used_mb": int(raw.get("_memory_used_mb") or 0),
    }


def _number_hosts(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numbered: list[dict[str, Any]] = []
    for idx, host in enumerate(hosts):
        numbered.append({**host, "host_index": idx + 1})
    return numbered


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
        "resource_source": unit.resource_source,
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
    constraints: list[dict[str, Any]] | None = None,
) -> list[str]:
    warnings: list[str] = []
    host_cpu, host_memory = _host_capacity(spec)

    for host in hosts:
        host_label = f"Host {host['host_index']}"
        cpu_used = float(host.get("cpu_used") or 0)
        memory_used = int(host.get("memory_used_mb") or 0)
        if cpu_used > host_cpu:
            over = cpu_used - host_cpu
            warnings.append(
                f"{host_label}: CPU demand exceeds usable capacity by {over:.2f} vCPU on {spec.machine_type}."
            )
        if memory_used > host_memory:
            over = memory_used - host_memory
            warnings.append(
                f"Selected {spec.machine_type} would exceed memory capacity by {over} MB."
            )
        disk_used = float(host.get("disk_used_gb") or 0)
        if disk_used > _HOST_BOOT_DISK_GB:
            over = round(disk_used - _HOST_BOOT_DISK_GB, 2)
            warnings.append(
                f"{host_label}: disk demand ({disk_used:.1f} GB) exceeds boot disk capacity "
                f"({_HOST_BOOT_DISK_GB:.0f} GB) by {over:.1f} GB."
            )

    if not packed:
        warnings.append(
            f"Insufficient capacity: selected machine type cannot fit all placement units "
            f"within {len(hosts)} host(s) ({spec.machine_type}: {host_cpu:.2f} vCPU, "
            f"{host_memory} MB usable per host)."
        )

    for unit in units:
        if unit.resource_cpu > host_cpu:
            warnings.append(
                f"Node '{unit.node_name}' requires {unit.resource_cpu} vCPU but {spec.machine_type} "
                f"only provides {host_cpu:.2f} vCPU usable per host."
            )
        if unit.resource_memory_mb > host_memory:
            over = unit.resource_memory_mb - host_memory
            warnings.append(
                f"Selected {spec.machine_type} would exceed memory capacity by {over} MB for node '{unit.node_name}'."
            )
        if unit.exposure == "public":
            ports = ", ".join(str(p) for p in unit.required_ports) or "default app ports"
            warnings.append(
                f"Public workload '{unit.node_name}' requires exposed ports: {ports}."
            )
        if unit.stateful:
            warnings.append(
                f"Stateful workload '{unit.node_name}' ({unit.resource_disk_gb:.1f} GB disk) requires persistent storage; "
                "the docker-vm template does not provision persistent volumes automatically."
            )
        if unit.placement_constraints:
            legacy_constraints = ", ".join(unit.placement_constraints)
            warnings.append(
                f"Legacy placement constraints ({legacy_constraints}) on '{unit.node_name}' are advisory; use topology placement constraints for enforced rules."
            )

    placement_by_ref: dict[str, int] = {}
    for host in hosts:
        host_index = int(host.get("host_index") or 0)
        for detail in host.get("assigned_node_details") or []:
            placement_by_ref[str(detail.get("node_id") or "")] = host_index
            placement_by_ref[str(detail.get("node_name") or "")] = host_index

    for constraint in constraints or []:
        ctype = str(constraint.get("constraint_type") or "")
        node_a = str(constraint.get("node_a") or "")
        node_b = str(constraint.get("node_b") or "")
        if ctype in {"same_host", "different_host"} and (not node_a or not node_b):
            warnings.append(f"Placement constraint '{ctype}' requires both node_a and node_b.")
            continue
        host_a = placement_by_ref.get(node_a)
        host_b = placement_by_ref.get(node_b)
        if ctype == "same_host" and host_a and host_b and host_a != host_b:
            warnings.append(f"same_host constraint could not be satisfied for '{node_a}' and '{node_b}'.")
        if ctype == "different_host" and host_a and host_b and host_a == host_b:
            warnings.append(f"different_host constraint could not be satisfied for '{node_a}' and '{node_b}'.")
        if ctype == "preferred_host":
            preferred = constraint.get("preferred_host")
            if preferred and host_a and int(preferred) != host_a:
                warnings.append(
                    f"preferred_host constraint for '{node_a}' requested Host {preferred}, but placement used Host {host_a}."
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
    if (
        len(hosts) == 1
        and not packed
        and total_memory > host_memory
        and not any("exceed memory capacity" in w for w in warnings)
    ):
        warnings.append(
            f"Selected {spec.machine_type} would exceed memory capacity by {total_memory - host_memory} MB."
        )
    if (
        len(hosts) == 1
        and not packed
        and total_cpu > host_cpu
        and not any("CPU demand exceeds" in w for w in warnings)
    ):
        warnings.append(
            f"Selected {spec.machine_type} would exceed CPU capacity by {total_cpu - host_cpu:.2f} vCPU."
        )

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            unique.append(warning)
    return unique


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
                "resource_source": meta.resource_source,
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
    placement_mode: str = "first_fit",
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    provider_key = (provider or _PROVIDER).strip().lower()
    if provider_key != "gcp":
        raise ValueError("Placement planner currently supports provider=gcp only.")
    mode = (placement_mode or "first_fit").strip().lower()
    if mode not in _PLACEMENT_MODES:
        raise ValueError(f"placement_mode must be one of: {', '.join(sorted(_PLACEMENT_MODES))}.")
    constraint_list = [dict(c) for c in (constraints or [])]

    estimate = build_resource_estimate(topology)
    units = expand_placement_units(topology)
    if not units:
        return {
            **estimate,
            "provider": provider_key,
            "placement_mode": mode,
            "recommended_host_count": 0,
            "host_count": 0,
            "recommended_machine_type": "e2-micro",
            "machine_rationale": "No workload nodes with resource metadata; defaulting to e2-micro.",
            "hosts": [],
            "warnings": ["No placement units found; add resource metadata to topology nodes."],
            "exposed_ports": [],
            "suggested_template_id": _TEMPLATE_ID,
            "constraints_used": constraint_list,
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

    hosts, packed = _bin_pack_units(
        units,
        spec,
        max_hosts=host_count,
        placement_mode=mode,
        constraints=constraint_list,
    )
    if not hosts:
        hosts, packed = _bin_pack_units(units, spec, placement_mode=mode, constraints=constraint_list)
    hosts = _number_hosts(hosts)

    recommended_host_count = len(hosts)
    warnings = _collect_warnings(
        units=units,
        hosts=hosts,
        spec=spec,
        packed=packed,
        selected_machine_type=machine_type,
        recommended_host_count=recommended_host_count,
        constraints=constraint_list,
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
        "placement_mode": mode,
        "recommended_host_count": recommended_host_count,
        "host_count": recommended_host_count,
        "recommended_machine_type": chosen_machine,
        "machine_rationale": rationale,
        "hosts": hosts,
        "placements": hosts,
        "warnings": warnings,
        "exposed_ports": exposed_ports,
        "suggested_template_id": _TEMPLATE_ID,
        "constraints_used": constraint_list,
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
    from app.services.infra_security import gcp_terraform_label_variables, sanitize_gcp_resource_name

    name_slug = sanitize_gcp_resource_name(topology.name)
    provider_key = str(plan.get("provider") or _PROVIDER).strip().lower()
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
        **gcp_terraform_label_variables(
            deployment_name=topology.name,
            template_id=_TEMPLATE_ID,
            provider=provider_key,
        ),
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
    placement_mode: str = "first_fit",
    constraints: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    credentials_ref: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    plan = build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
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
    warning_text = " ".join(plan.get("warnings") or [])
    if any(
        phrase in warning_text
        for phrase in (
            "Insufficient capacity",
            "exceed memory capacity",
            "exceed CPU capacity",
            "CPU demand exceeds",
        )
    ):
        capacity_status = "insufficient_capacity"

    placement_summary = {
        "recommended_machine_type": plan.get("recommended_machine_type"),
        "recommended_host_count": plan.get("recommended_host_count"),
        "hosts": [
            {
                "host_index": host.get("host_index"),
                "machine_type": host.get("machine_type"),
                "assigned_nodes": host.get("assigned_nodes") or [],
                "cpu_used": host.get("cpu_used"),
                "cpu_capacity": host.get("cpu_capacity"),
                "memory_used_mb": host.get("memory_used_mb"),
                "memory_capacity_mb": host.get("memory_capacity_mb"),
            }
            for host in plan.get("hosts") or []
        ],
        "warnings": plan.get("warnings") or [],
        "placement_mode": plan.get("placement_mode"),
        "constraints_used": plan.get("constraints_used") or [],
    }

    return {
        "name": deployment_name,
        "template_id": template_id,
        "provider": plan["provider"],
        "variables": merged_vars,
        "credentials_ref": cred_ref,
        "placement_plan": plan,
        "placement_summary": placement_summary,
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
