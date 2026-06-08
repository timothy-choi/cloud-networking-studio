"""Runtime package import / rehydrate service (Step 66)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.models.user import User
from app.services.access_control import default_project_for_user, require_project_editor
from app.services import topology_placement_persistence_service as placement_persist_svc
from app.services.runtime_package_export_service import _sanitize_compose_service_name

_REQUIRED_MANIFEST = "deployment-manifest.json"
_REQUIRED_HOST_PLACEMENT = "host-placement.json"
_MAX_ZIP_BYTES = 10 * 1024 * 1024
_MAX_ZIP_FILES = 64
_ALLOWED_EXTENSIONS = frozenset({".json", ".yml", ".yaml", ".md", ".example", ".env"})


@dataclass
class ComposeService:
    name: str
    image: str | None = None
    ipv4_address: str | None = None
    network_name: str | None = None
    ports: list[int] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    command: list[str] | None = None
    health_check: dict[str, Any] | None = None


@dataclass
class ParsedCompose:
    services: dict[str, ComposeService]
    network_name: str
    subnet: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zip_member_name(name: str) -> str:
    normalized = name.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError(f"Unsafe path in runtime package ZIP: {name!r}")
    return normalized


def _allowed_member_name(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    if base.startswith("."):
        return base in {".env.example"}
    lower = base.lower()
    for ext in _ALLOWED_EXTENSIONS:
        if lower.endswith(ext) or lower == ext.lstrip("."):
            return True
    return lower in {
        "docker-compose.yml",
        "docker-compose.yaml",
        "deployment-manifest.json",
        "host-placement.json",
        "readme.md",
        "manifest-summary.json",
    }


def extract_zip_package(zip_bytes: bytes) -> dict[str, bytes]:
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise ValueError(f"Runtime package ZIP exceeds {_MAX_ZIP_BYTES // (1024 * 1024)} MB limit.")
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [info for info in zf.infolist() if not info.is_dir()]
        if not members:
            raise ValueError("Runtime package ZIP is empty.")
        if len(members) > _MAX_ZIP_FILES:
            raise ValueError("Runtime package ZIP contains too many files.")
        for info in members:
            safe_name = _safe_zip_member_name(info.filename)
            if not _allowed_member_name(safe_name):
                raise ValueError(f"Unexpected file in runtime package ZIP: {safe_name}")
            if info.file_size > _MAX_ZIP_BYTES:
                raise ValueError(f"File too large in runtime package ZIP: {safe_name}")
            files[safe_name] = zf.read(info)
    return files


def _decode_text(payload: bytes) -> str:
    return payload.decode("utf-8")


def _parse_json_file(files: dict[str, bytes], name: str) -> dict[str, Any]:
    key = next((k for k in files if k.endswith(name) or k == name), None)
    if key is None:
        raise ValueError(f"Missing required file: {name}")
    try:
        data = json.loads(_decode_text(files[key]))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a JSON object.")
    return data


def _strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _parse_json_array(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _parse_healthcheck_block(lines: list[str]) -> dict[str, Any] | None:
    test_line = next((line for line in lines if line.strip().startswith("test:")), None)
    if not test_line:
        return None
    test_value = test_line.split(":", 1)[1].strip()
    parts = _parse_json_array(test_value)
    if not parts:
        return None
    if parts[0] in {"CMD", "CMD-SHELL"}:
        body = parts[1:] if parts[0] == "CMD" else [" ".join(parts[1:])]
        if not body:
            return None
        joined = " ".join(body)
        if "wget" in joined and "http://localhost:" in joined:
            m = re.search(r"http://localhost:(\d+)(/.*)?", joined)
            if m:
                return {
                    "check_type": "http",
                    "port": int(m.group(1)),
                    "path": m.group(2) or "/",
                }
        if "nc -z localhost" in joined:
            m = re.search(r"nc -z localhost (\d+)", joined)
            if m:
                return {"check_type": "tcp", "port": int(m.group(1))}
        return {"check_type": "command", "command": body if parts[0] == "CMD" else body[0]}
    return None


def parse_docker_compose(text: str) -> ParsedCompose:
    if not text.strip():
        raise ValueError("docker-compose.yml is empty.")
    if "services:" not in text:
        raise ValueError("docker-compose.yml is missing a services section.")

    services: dict[str, ComposeService] = {}
    network_name = "cns-net"
    subnet: str | None = None
    section: str | None = None
    current_service: str | None = None
    nested: str | None = None
    health_lines: list[str] = []
    in_health = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "services:" and not line.startswith(" "):
            section = "services"
            current_service = None
            nested = None
            in_health = False
            continue
        if stripped == "networks:" and not line.startswith(" "):
            if in_health and current_service:
                services[current_service].health_check = _parse_healthcheck_block(health_lines)
                in_health = False
                health_lines = []
            section = "networks"
            current_service = None
            nested = None
            continue

        if section == "networks":
            if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
                network_name = stripped[:-1]
            if "subnet:" in stripped:
                subnet = _strip_yaml_scalar(stripped.split("subnet:", 1)[1])
            continue

        if section != "services":
            continue

        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            if in_health and current_service:
                services[current_service].health_check = _parse_healthcheck_block(health_lines)
            current_service = stripped[:-1]
            services[current_service] = ComposeService(name=current_service)
            nested = None
            in_health = False
            health_lines = []
            continue

        if current_service is None:
            continue

        svc = services[current_service]
        indent = len(line) - len(line.lstrip(" "))

        if stripped == "healthcheck:":
            in_health = True
            health_lines = []
            continue
        if in_health:
            if indent >= 6:
                health_lines.append(line)
                continue
            svc.health_check = _parse_healthcheck_block(health_lines)
            in_health = False
            health_lines = []

        if stripped.startswith("image:"):
            svc.image = _strip_yaml_scalar(stripped.split(":", 1)[1])
        elif stripped.startswith("command:"):
            svc.command = _parse_json_array(stripped.split(":", 1)[1]) or None
        elif stripped == "ports:":
            nested = "ports"
        elif nested == "ports" and stripped.startswith("- "):
            port_raw = stripped[2:].strip().strip('"').strip("'")
            host_port = port_raw.split(":", 1)[0]
            try:
                svc.ports.append(int(host_port))
            except ValueError:
                pass
        elif stripped == "environment:":
            nested = "environment"
        elif nested == "environment" and ":" in stripped:
            key, _, value = stripped.partition(":")
            svc.environment[key.strip()] = _strip_yaml_scalar(value)
        elif stripped == "networks:":
            nested = "networks"
        elif nested == "networks" and stripped.endswith(":"):
            svc.network_name = stripped[:-1]
            nested = "network_ip"
        elif nested == "network_ip" and stripped.startswith("ipv4_address:"):
            svc.ipv4_address = _strip_yaml_scalar(stripped.split(":", 1)[1])
        elif indent <= 4:
            nested = None

    if in_health and current_service and current_service in services:
        services[current_service].health_check = _parse_healthcheck_block(health_lines)

    if not services:
        raise ValueError("docker-compose.yml contains no services.")
    return ParsedCompose(services=services, network_name=network_name, subnet=subnet)


def _runtime_target_for_strategy(strategy_id: str) -> str:
    if strategy_id == "k8s-cluster":
        return "kubernetes"
    return "docker"


def _node_details_index(placement_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for host in placement_plan.get("hosts") or []:
        for detail in host.get("assigned_node_details") or []:
            name = str(detail.get("node_name") or detail.get("display_name") or "").strip()
            if name:
                out[name] = dict(detail)
    return out


def _match_compose_service(node_name: str, compose: ParsedCompose) -> ComposeService | None:
    target = _sanitize_compose_service_name(node_name)
    if target in compose.services:
        return compose.services[target]
    for suffix in range(2, 10):
        candidate = f"{target}-{suffix}"
        if candidate in compose.services:
            return compose.services[candidate]
    for service_name, service in compose.services.items():
        if service_name == target or service_name.startswith(f"{target}-"):
            return service
    return None


def _build_node_config(
    *,
    resource: dict[str, Any] | None,
    detail: dict[str, Any] | None,
    compose_svc: ComposeService | None,
) -> dict[str, Any]:
    resource = resource or {}
    detail = detail or {}
    config: dict[str, Any] = {
        "resource_cpu": float(resource.get("resource_cpu") or detail.get("resource_cpu") or 0.25),
        "resource_memory_mb": int(resource.get("resource_memory_mb") or detail.get("resource_memory_mb") or 256),
        "resource_disk_gb": float(resource.get("resource_disk_gb") or detail.get("resource_disk_gb") or 5),
        "replicas": int(resource.get("replicas") or detail.get("replicas") or 1),
        "node_role": str(resource.get("node_role") or detail.get("node_role") or "workload"),
        "exposure": str(resource.get("exposure") or detail.get("exposure") or "internal"),
        "stateful": bool(resource.get("stateful") if "stateful" in resource else detail.get("stateful", False)),
    }
    ports = list(detail.get("required_ports") or [])
    if compose_svc and compose_svc.ports:
        ports = sorted(set(ports) | set(compose_svc.ports))
    if ports:
        config["required_ports"] = ports
        if compose_svc and compose_svc.ports:
            config["exposure"] = "public"
    if compose_svc and compose_svc.health_check:
        config["health_check"] = compose_svc.health_check
    if compose_svc and compose_svc.environment:
        config["env"] = compose_svc.environment
    if compose_svc and compose_svc.command:
        config["command"] = compose_svc.command
    return config


def _remap_plan_node_ids(plan: dict[str, Any], name_to_id: dict[str, UUID]) -> dict[str, Any]:
    remapped = json.loads(json.dumps(plan))
    for node in remapped.get("nodes") or []:
        node_name = str(node.get("node_name") or "").strip()
        if node_name in name_to_id:
            node["node_id"] = str(name_to_id[node_name])
    for host in remapped.get("hosts") or []:
        for detail in host.get("assigned_node_details") or []:
            node_name = str(detail.get("node_name") or "").strip()
            if node_name in name_to_id:
                detail["node_id"] = str(name_to_id[node_name])
    return remapped


def _create_links_for_nodes(
    db: Session,
    *,
    topology_id: UUID,
    node_ids: list[UUID],
    network_name: str,
    subnet: str | None,
    link_count_hint: int,
) -> int:
    if len(node_ids) < 2 or link_count_hint <= 0:
        return 0
    created = 0
    for idx in range(len(node_ids) - 1):
        link = TopologyLink(
            topology_id=topology_id,
            source_node_id=node_ids[idx],
            target_node_id=node_ids[idx + 1],
            network_name=network_name[:255],
            cidr=(subnet[:64] if subnet else None),
        )
        db.add(link)
        created += 1
    return created


def import_runtime_package(
    db: Session,
    *,
    user: User,
    zip_bytes: bytes,
    project_id: UUID | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Parse a runtime package ZIP and recreate topology planning metadata. Never executes package files."""
    files = extract_zip_package(zip_bytes)
    manifest = _parse_json_file(files, _REQUIRED_MANIFEST)
    host_placement = _parse_json_file(files, _REQUIRED_HOST_PLACEMENT)

    compose_key = next(
        (k for k in files if k.endswith("docker-compose.yml") or k.endswith("docker-compose.yaml")),
        None,
    )
    compose: ParsedCompose | None = None
    if compose_key is not None:
        compose = parse_docker_compose(_decode_text(files[compose_key]))

    strategy_id = str(manifest.get("strategy_id") or "docker-vm")
    placement_plan = dict(manifest.get("placement_plan") or {})
    if not placement_plan.get("hosts") and host_placement.get("hosts"):
        placement_plan["hosts"] = host_placement["hosts"]
    for key in ("provider", "placement_mode", "recommended_machine_type", "recommended_host_count"):
        if key not in placement_plan and key in host_placement:
            placement_plan[key] = host_placement[key]

    placement_nodes = list(placement_plan.get("nodes") or [])
    if not placement_nodes and compose is not None:
        placement_nodes = [{"node_name": svc_name} for svc_name in sorted(compose.services)]
    if not placement_nodes:
        raise ValueError("Runtime package does not contain any node definitions to import.")

    pid = project_id
    if pid is None:
        proj = default_project_for_user(db, user)
        if proj is None:
            raise ValueError("Create a project first, or pass project_id.")
        pid = proj.id
    require_project_editor(db, user, pid)

    topo_name = (name or "").strip() or str(manifest.get("topology_name") or "Imported topology")
    if not (name or "").strip():
        topo_name = f"{topo_name} (imported)"

    topo = Topology(
        project_id=pid,
        name=topo_name[:255],
        description=f"Imported from runtime package ({strategy_id}).",
        status=TopologyStatus.DRAFT,
        runtime_target=_runtime_target_for_strategy(strategy_id),
        networking_mode="docker_bridge",
        config={
            "imported_from_runtime_package": True,
            "source_topology_id": manifest.get("topology_id"),
            "source_strategy_id": strategy_id,
            "imported_at": _utc_now().isoformat(),
            "package_files": sorted(files.keys()),
        },
    )
    db.add(topo)
    db.flush()

    details_by_name = _node_details_index(placement_plan)
    resources_by_name = {
        str(row.get("node_name") or "").strip(): row for row in placement_nodes if row.get("node_name")
    }
    name_to_id: dict[str, UUID] = {}
    created_nodes: list[TopologyNode] = []

    for row in placement_nodes:
        node_name = str(row.get("node_name") or "").strip()
        if not node_name:
            continue
        compose_svc = _match_compose_service(node_name, compose) if compose else None
        config = _build_node_config(
            resource=resources_by_name.get(node_name),
            detail=details_by_name.get(node_name),
            compose_svc=compose_svc,
        )
        image = (compose_svc.image if compose_svc and compose_svc.image else None) or "alpine:latest"
        ip_address = compose_svc.ipv4_address if compose_svc else None
        node = TopologyNode(
            topology_id=topo.id,
            name=node_name[:255],
            node_type=NodeType.HOST,
            image=image[:512],
            ip_address=(ip_address[:64] if ip_address else None),
            config=config,
        )
        db.add(node)
        db.flush()
        name_to_id[node_name] = node.id
        created_nodes.append(node)

    if not created_nodes:
        raise ValueError("Failed to recreate any topology nodes from runtime package.")

    network_name = compose.network_name if compose else "cns-net"
    subnet = compose.subnet if compose else None
    node_ids = [node.id for node in created_nodes]
    links_created = _create_links_for_nodes(
        db,
        topology_id=topo.id,
        node_ids=node_ids,
        network_name=network_name,
        subnet=subnet,
        link_count_hint=int(manifest.get("link_count") or 0),
    )

    constraints_created = 0
    for constraint in host_placement.get("placement_constraints") or []:
        if not isinstance(constraint, dict):
            continue
        constraint_type = str(constraint.get("constraint_type") or "").strip()
        node_a = str(constraint.get("node_a") or "").strip()
        if not constraint_type or not node_a:
            continue
        node_b = str(constraint.get("node_b") or "").strip() or None
        preferred_host = constraint.get("preferred_host")
        try:
            preferred_host = int(preferred_host) if preferred_host is not None else None
        except (TypeError, ValueError):
            preferred_host = None
        placement_persist_svc.create_constraint(
            db,
            topology_id=topo.id,
            project_id=pid,
            actor=user,
            constraint_type=constraint_type,
            node_a=node_a,
            node_b=node_b,
            preferred_host=preferred_host,
        )
        constraints_created += 1

    remapped_plan = _remap_plan_node_ids(placement_plan, name_to_id)
    saved_plan = placement_persist_svc.save_plan(
        db,
        topology_id=topo.id,
        project_id=pid,
        actor=user,
        plan=remapped_plan,
    )

    warnings = list(manifest.get("warnings") or [])
    if compose is None:
        warnings.append("docker-compose.yml was not present; images and network settings may be incomplete.")

    return {
        "topology_id": str(topo.id),
        "project_id": str(pid),
        "name": topo.name,
        "strategy_id": strategy_id,
        "node_count": len(created_nodes),
        "link_count": links_created,
        "placement_plan_id": str(saved_plan.id),
        "files_imported": sorted(files.keys()),
        "warnings": warnings,
        "planning_only": bool(manifest.get("planning_only")),
    }
