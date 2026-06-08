"""Runtime package export service (Step 65).

Generates downloadable deployment packages from topology, placement plan, and runtime strategy.
"""

from __future__ import annotations

import io
import ipaddress
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.topology import Topology
from app.services import cost_capacity_advisor_service as cost_svc
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services import topology_placement_persistence_service as placement_persist_svc
from app.services import topology_placement_planner_service as placement_svc
from app.services.node_resource_metadata import extract_node_resource_metadata
from app.services.node_runtime_config import extract_node_runtime_config, normalize_health_check, primary_port
from app.services.runtime_strategy_registry import get_runtime_strategy, require_runtime_strategy
from app.services.runtime_strategy_plan_service import build_runtime_strategy_plan
from app.services.topology_iac_export_service import (
    _compose_command_for_node,
    _format_compose_command_array,
    _image_repo_name,
    _is_alpine_like_image,
    _is_idle_workload_node,
    _is_service_image,
    _yaml_scalar,
    ExportNode,
)

_PACKAGE_ROOT = Path("/tmp/cns-runtime-packages")
_DEFAULT_SUBNET = "10.50.0.0/24"
_DEFAULT_NETWORK = "cns-net"


@dataclass
class RuntimePackageRecord:
    package_id: str
    topology_id: UUID
    project_id: UUID
    strategy_id: str
    status: str
    files: list[str]
    zip_path: Path
    created_at: datetime
    user_id: UUID
    planning_only: bool = False


_REGISTRY: dict[str, RuntimePackageRecord] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_compose_service_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9_-]+", "-", (name or "node").lower()).strip("-")
    base = re.sub(r"-+", "-", base)[:48]
    if not base:
        base = "node"
    if base[0].isdigit():
        base = f"n-{base}"
    return base


def _unique_service_names(nodes: list[Any]) -> dict[UUID, str]:
    used: dict[str, int] = {}
    out: dict[UUID, str] = {}
    for node in nodes:
        base = _sanitize_compose_service_name(node.name)
        count = used.get(base, 0) + 1
        used[base] = count
        out[node.id] = base if count == 1 else f"{base}-{count}"
    return out


def _topology_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "topology").lower()).strip("-") or "topology"
    return slug[:32]


def _resolve_subnet(topology: Topology) -> str:
    for link in topology.links or []:
        cidr = (link.cidr or "").strip()
        if cidr:
            try:
                ipaddress.ip_network(cidr, strict=False)
                return cidr
            except ValueError:
                continue
    return _DEFAULT_SUBNET


def _resolve_network_name(topology: Topology) -> str:
    for link in topology.links or []:
        net = (link.network_name or "").strip()
        if net:
            return re.sub(r"[^a-zA-Z0-9_.-]+", "-", net).strip("-") or _DEFAULT_NETWORK
    return _DEFAULT_NETWORK


def _validate_ip_addresses(topology: Topology) -> None:
    seen: dict[str, str] = {}
    for node in topology.nodes or []:
        ip_raw = (node.ip_address or "").strip()
        if not ip_raw:
            continue
        try:
            ipaddress.ip_address(ip_raw)
        except ValueError as exc:
            raise ValueError(f"Node '{node.name}' has invalid ip_address '{ip_raw}'.") from exc
        if ip_raw in seen:
            raise ValueError(f"Duplicate IP address '{ip_raw}' on nodes '{seen[ip_raw]}' and '{node.name}'.")
        seen[ip_raw] = node.name


def _validate_required_ports(topology: Topology) -> None:
    for node in topology.nodes or []:
        meta = extract_node_resource_metadata(node)
        if meta is None:
            continue
        for port in meta.required_ports:
            if port <= 0 or port > 65535:
                raise ValueError(
                    f"Node '{node.name}' has invalid required_ports entry {port}; ports must be 1-65535."
                )


def _workload_nodes(topology: Topology) -> list[Any]:
    nodes: list[Any] = []
    for node in topology.nodes or []:
        meta = extract_node_resource_metadata(node)
        if meta is not None:
            nodes.append(node)
    return nodes


def validate_runtime_package_request(topology: Topology, strategy_id: str) -> None:
    if not topology.nodes:
        raise ValueError("Topology must have at least one node before exporting a runtime package.")
    require_runtime_strategy(strategy_id)
    _validate_ip_addresses(topology)
    _validate_required_ports(topology)
    if strategy_id == "docker-vm":
        workload = _workload_nodes(topology)
        if not workload:
            raise ValueError("docker-vm runtime package requires at least one workload node with resource metadata.")
        missing = [node.name for node in workload if not (node.image or "").strip()]
        if missing:
            raise ValueError(
                f"docker-vm runtime package requires container images on all workload nodes; missing: {', '.join(missing)}."
            )


def _allocate_ips(nodes: list[Any], subnet_cidr: str) -> dict[UUID, str]:
    network = ipaddress.ip_network(subnet_cidr, strict=False)
    hosts = list(network.hosts())
    if len(hosts) < 2:
        raise ValueError(f"Subnet '{subnet_cidr}' is too small for container IP allocation.")
    reserved = {str(network.network_address), str(network.broadcast_address)}
    assigned: dict[UUID, str] = {}
    used: set[str] = set()

    for node in nodes:
        ip_raw = (node.ip_address or "").strip()
        if ip_raw:
            try:
                ip = ipaddress.ip_address(ip_raw)
            except ValueError:
                ip_raw = ""
            else:
                if ip not in network:
                    raise ValueError(
                        f"Node '{node.name}' ip_address '{ip_raw}' is outside subnet '{subnet_cidr}'."
                    )
                if ip_raw in used or ip_raw in reserved:
                    raise ValueError(f"Node '{node.name}' ip_address '{ip_raw}' conflicts with another assignment.")
                assigned[node.id] = ip_raw
                used.add(ip_raw)

    cursor = 10
    for node in nodes:
        if node.id in assigned:
            continue
        while cursor < 250:
            candidate = str(network.network_address + cursor)
            cursor += 10
            if candidate in used or candidate in reserved:
                continue
            assigned[node.id] = candidate
            used.add(candidate)
            break
        else:
            raise ValueError(f"Unable to allocate IP addresses for all nodes in subnet '{subnet_cidr}'.")
    return assigned


def _export_node(node: Any, service_name: str) -> ExportNode:
    runtime = extract_node_runtime_config(node.config)
    node_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
    return ExportNode(
        id=node.id,
        name=node.name,
        node_type=node_type,
        image=node.image,
        ip_address=node.ip_address,
        service_name=service_name,
        runtime=runtime,
        health_check=runtime.health_check,
    )


def _compose_healthcheck_lines(node: ExportNode) -> list[str]:
    runtime = node.runtime
    primary = primary_port(runtime) if runtime.ports else 80
    hc = normalize_health_check(
        runtime.health_check,
        image=node.image,
        primary_port=primary,
        has_explicit_ports=bool(runtime.ports),
    )
    if not hc:
        return []
    check_type = str(hc.get("check_type") or "http")
    if check_type == "command":
        cmd = hc.get("command")
        if isinstance(cmd, list) and cmd:
            test = ["CMD", *cmd]
        elif isinstance(cmd, str) and cmd.strip():
            test = ["CMD-SHELL", cmd.strip()]
        else:
            return []
    elif check_type == "tcp":
        port = int(hc.get("port") or primary or 80)
        test = ["CMD-SHELL", f"nc -z localhost {port} || exit 1"]
    elif check_type == "http":
        port = int(hc.get("port") or primary or 80)
        path = str(hc.get("path") or "/")
        test = ["CMD", "wget", "-qO-", f"http://localhost:{port}{path}"]
    else:
        return []
    interval = str(hc.get("interval") or "10s")
    timeout = str(hc.get("timeout") or "5s")
    retries = int(hc.get("retries") or 5)
    return [
        "    healthcheck:",
        f"      test: {_format_compose_command_array(test)}",
        f"      interval: {interval}",
        f"      timeout: {timeout}",
        f"      retries: {retries}",
    ]


def _idle_export_node(node: ExportNode) -> bool:
    return _is_idle_workload_node(node) and _is_alpine_like_image(node.image) and not _is_service_image(node.image)


def generate_docker_compose(
    topology: Topology,
    *,
    network_name: str | None = None,
    subnet_cidr: str | None = None,
) -> str:
    workload = _workload_nodes(topology)
    service_names = _unique_service_names(workload)
    net = network_name or _resolve_network_name(topology)
    subnet = subnet_cidr or _resolve_subnet(topology)
    ip_map = _allocate_ips(workload, subnet)
    slug = _topology_slug(topology.name)

    lines = [
        "# Generated by Cloud Networking Studio — runtime deployment package.",
        f"# Topology: {topology.name} ({topology.id})",
        "services:",
    ]
    for node in workload:
        export_node = _export_node(node, service_names[node.id])
        lines.append(f"  {export_node.service_name}:")
        lines.append(f"    image: {_yaml_scalar(export_node.image or 'alpine:latest')}")
        lines.append(f"    container_name: cns-{slug}-{export_node.service_name}")
        command_parts = _compose_command_for_node(export_node)
        if command_parts:
            lines.append(f"    command: {_format_compose_command_array(command_parts)}")
        elif _idle_export_node(export_node):
            lines.append(f"    command: {_format_compose_command_array(['sleep', 'infinity'])}")

        meta = extract_node_resource_metadata(node)
        if meta and meta.exposure == "public" and meta.required_ports:
            lines.append("    ports:")
            for port in meta.required_ports:
                lines.append(f'      - "{port}:{port}"')

        if export_node.runtime.env:
            lines.append("    environment:")
            for key, value in export_node.runtime.env.items():
                lines.append(f"      {key}: {_yaml_scalar(str(value))}")

        lines.extend(_compose_healthcheck_lines(export_node))

        ip = ip_map[node.id]
        lines.append("    networks:")
        lines.append(f"      {net}:")
        lines.append(f"        ipv4_address: {ip}")

    lines.extend(
        [
            "networks:",
            f"  {net}:",
            "    driver: bridge",
            "    ipam:",
            "      config:",
            f"        - subnet: {subnet}",
            "",
        ]
    )
    return "\n".join(lines)


def generate_env_example(topology: Topology) -> str:
    slug = _topology_slug(topology.name)
    lines = [
        "# Copy to .env and adjust values before running docker compose.",
        f"COMPOSE_PROJECT_NAME=cns-{slug}",
        f"CNS_TOPOLOGY_ID={topology.id}",
        f"CNS_TOPOLOGY_NAME={topology.name}",
        "",
    ]
    for node in _workload_nodes(topology):
        runtime = extract_node_runtime_config(node.config)
        if runtime.env:
            lines.append(f"# Environment overrides for {node.name}")
            for key in runtime.env:
                lines.append(f"# {key}=")
            lines.append("")
    return "\n".join(lines)


def build_deployment_manifest(
    *,
    topology: Topology,
    strategy_id: str,
    placement_plan: dict[str, Any],
    cost_estimate: dict[str, Any],
    runtime_plan: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    strategy = require_runtime_strategy(strategy_id)
    return {
        "topology_id": str(topology.id),
        "topology_name": topology.name,
        "strategy_id": strategy_id,
        "runtime_provider": strategy.runtime_provider,
        "generated_at": generated_at.isoformat(),
        "node_count": len(topology.nodes or []),
        "link_count": len(topology.links or []),
        "resource_estimate": {
            "total_cpu": placement_plan.get("total_cpu"),
            "total_memory_mb": placement_plan.get("total_memory_mb"),
            "total_disk_gb": placement_plan.get("total_disk_gb"),
            "workload_node_count": placement_plan.get("workload_node_count"),
            "placement_unit_count": placement_plan.get("placement_unit_count"),
        },
        "placement_plan": placement_plan,
        "cost_estimate": cost_estimate,
        "warnings": list(placement_plan.get("warnings") or []),
        "unsupported_features": list(runtime_plan.get("unsupported_features") or []),
        "runtime_strategy": runtime_plan.get("runtime_strategy"),
        "planning_only": strategy.status in ("planning_only", "future"),
    }


def build_host_placement(
    placement_plan: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    hosts = placement_plan.get("hosts") or []
    return {
        "host_count": len(hosts) or int(placement_plan.get("recommended_host_count") or 0),
        "provider": placement_plan.get("provider"),
        "placement_mode": placement_plan.get("placement_mode"),
        "recommended_machine_type": placement_plan.get("recommended_machine_type"),
        "hosts": hosts,
        "placement_constraints": constraints,
    }


def generate_readme(
    *,
    topology: Topology,
    strategy_id: str,
    files: list[str],
    planning_only: bool,
    limitations: list[str],
    runtime_plan: dict[str, Any],
) -> str:
    strategy = require_runtime_strategy(strategy_id)
    lines = [
        "# Cloud Networking Studio — Runtime Deployment Package",
        "",
        f"Topology: **{topology.name}** (`{topology.id}`)",
        f"Runtime strategy: **{strategy.display_name}** (`{strategy.id}`)",
        f"Status: {strategy.status}",
        "",
        "## Generated artifacts",
        "",
    ]
    for filename in files:
        lines.append(f"- `{filename}`")
    lines.append("")

    if planning_only:
        lines.extend(
            [
                "## Planning-only package",
                "",
                "This package captures placement and strategy planning artifacts only. "
                "It is **not directly runnable** as a multi-host or Kubernetes deployment yet.",
                "",
            ]
        )
        if limitations:
            lines.append("### Known limitations")
            lines.append("")
            for item in limitations:
                lines.append(f"- {item}")
            lines.append("")
    else:
        lines.extend(
            [
                "## How to run locally",
                "",
                "1. Copy `.env.example` to `.env` and adjust values if needed.",
                "2. From this directory, start the stack:",
                "",
                "   ```bash",
                "   docker compose up -d",
                "   ```",
                "",
                "## How to validate",
                "",
                "```bash",
                "docker compose ps",
                "docker compose logs",
                "```",
                "",
            ]
        )

    unsupported = runtime_plan.get("unsupported_features") or []
    if unsupported:
        lines.extend(["## Unsupported features", ""])
        for item in unsupported:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## Strategy details",
            "",
            f"- Runtime provider: `{strategy.runtime_provider}`",
            f"- Host model: `{strategy.host_model}`",
            f"- Deployment model: `{strategy.deployment_model}`",
            f"- Placement hosts: {runtime_plan.get('host_count', 0)}",
            "",
            "Generated by Cloud Networking Studio. Existing infrastructure deployment flows in CNS are unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_k8s_placeholder_manifest(topology: Topology, strategy_id: str) -> str:
    strategy = require_runtime_strategy(strategy_id)
    summary = {
        "topology_id": str(topology.id),
        "topology_name": topology.name,
        "strategy_id": strategy_id,
        "runtime_provider": strategy.runtime_provider,
        "note": "Kubernetes manifest generation is not implemented yet.",
        "planned_workloads": [node.name for node in (topology.nodes or [])],
    }
    return json.dumps(summary, indent=2) + "\n"


def _create_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _store_package(
    *,
    topology: Topology,
    strategy_id: str,
    status: str,
    files: dict[str, str],
    user_id: UUID,
    planning_only: bool,
) -> RuntimePackageRecord:
    package_id = str(uuid.uuid4())
    _PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    zip_path = _PACKAGE_ROOT / f"{package_id}.zip"
    zip_path.write_bytes(_create_zip(files))
    record = RuntimePackageRecord(
        package_id=package_id,
        topology_id=topology.id,
        project_id=topology.project_id,
        strategy_id=strategy_id,
        status=status,
        files=sorted(files.keys()),
        zip_path=zip_path,
        created_at=_utc_now(),
        user_id=user_id,
        planning_only=planning_only,
    )
    _REGISTRY[package_id] = record
    return record


def get_package_record(package_id: str) -> RuntimePackageRecord | None:
    record = _REGISTRY.get(package_id)
    if record is not None and record.zip_path.is_file():
        return record
    candidate = _PACKAGE_ROOT / f"{package_id}.zip"
    if candidate.is_file():
        return RuntimePackageRecord(
            package_id=package_id,
            topology_id=UUID(int=0),
            project_id=UUID(int=0),
            strategy_id="",
            status="generated",
            files=[],
            zip_path=candidate,
            created_at=_utc_now(),
            user_id=UUID(int=0),
        )
    return None


def read_package_zip(package_id: str) -> bytes:
    record = get_package_record(package_id)
    if record is None:
        raise ValueError("Runtime package not found.")
    return record.zip_path.read_bytes()


def generate_runtime_package(
    topology: Topology,
    *,
    db: Session,
    strategy_id: str,
    provider: str = "gcp",
    machine_type: str | None = None,
    placement_mode: str = "first_fit",
    host_count: int | None = None,
    user_id: UUID,
) -> dict[str, Any]:
    strategy_id = (strategy_id or "docker-vm").strip()
    strategy = require_runtime_strategy(strategy_id)
    validate_runtime_package_request(topology, strategy_id)

    constraints = placement_persist_svc.constraints_as_dicts(db, topology.id)
    placement_plan = placement_svc.build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
    )
    plan_host_count = len(placement_plan.get("hosts") or []) or int(
        placement_plan.get("recommended_host_count") or 0
    )
    if strategy_id == "docker-vm" and plan_host_count != 1:
        raise ValueError(
            f"docker-vm runtime package requires a single-host placement plan (got {plan_host_count} hosts)."
        )

    strategy_recommendation = strategy_svc.build_strategy_recommendation(
        topology,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        placement_mode=placement_mode,
        constraints=constraints,
    )
    runtime_plan = build_runtime_strategy_plan(
        placement_plan=placement_plan,
        strategy_recommendation=strategy_recommendation,
        constraints=constraints,
        selected_strategy_id=strategy_id,
    )
    cost_estimate = cost_svc.build_cost_capacity_analysis(
        placement_plan,
        provider=provider,
        machine_type=machine_type,
        host_count=host_count,
        runtime_strategy_id=strategy_id,
    )

    generated_at = _utc_now()
    planning_only = strategy.status in ("planning_only", "future")
    limitations = list(runtime_plan.get("unsupported_features") or [])
    if planning_only:
        limitations.insert(
            0,
            f"Runtime strategy '{strategy.display_name}' is {strategy.status.replace('_', ' ')} "
            "and cannot be executed directly yet.",
        )

    manifest = build_deployment_manifest(
        topology=topology,
        strategy_id=strategy_id,
        placement_plan=placement_plan,
        cost_estimate=cost_estimate,
        runtime_plan=runtime_plan,
        generated_at=generated_at,
    )
    host_placement = build_host_placement(placement_plan, constraints)

    files: dict[str, str] = {
        "deployment-manifest.json": json.dumps(manifest, indent=2) + "\n",
        "host-placement.json": json.dumps(host_placement, indent=2) + "\n",
    }

    if strategy_id == "docker-vm" and not planning_only:
        files["docker-compose.yml"] = generate_docker_compose(topology)
        files[".env.example"] = generate_env_example(topology)
    elif strategy_id == "k8s-cluster":
        files["manifest-summary.json"] = _build_k8s_placeholder_manifest(topology, strategy_id)

    readme_files = sorted(files.keys())
    files["README.md"] = generate_readme(
        topology=topology,
        strategy_id=strategy_id,
        files=readme_files + ["README.md"],
        planning_only=planning_only,
        limitations=limitations,
        runtime_plan=runtime_plan,
    )

    status = "planning_only" if planning_only else "generated"
    record = _store_package(
        topology=topology,
        strategy_id=strategy_id,
        status=status,
        files=files,
        user_id=user_id,
        planning_only=planning_only,
    )

    return {
        "package_id": record.package_id,
        "strategy_id": strategy_id,
        "status": status,
        "files": record.files,
        "download_url": f"/api/runtime-packages/{record.package_id}/download",
        "planning_only": planning_only,
        "limitations": limitations,
    }


def clear_package_registry_for_tests() -> None:
    """Test helper to reset in-memory registry."""
    _REGISTRY.clear()
