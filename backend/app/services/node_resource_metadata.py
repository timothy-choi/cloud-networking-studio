"""Generic resource and placement metadata stored on topology node ``config`` JSON."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.topology import TopologyNode
from app.services.node_runtime_config import NodeConfigValidationError, extract_node_runtime_config

NODE_ROLES = frozenset(
    {"workload", "router", "gateway", "storage", "database", "cache", "queue", "custom"}
)
EXPOSURE_VALUES = frozenset({"public", "private", "internal"})
SUPPORTED_PLACEMENT_CONSTRAINTS = frozenset({"same_host", "separate_host", "anti_affinity"})

_DEFAULT_CPU = 0.5
_DEFAULT_MEMORY_MB = 512
_DEFAULT_DISK_GB = 5.0
_DEFAULT_REPLICAS = 1

_IMAGE_HEURISTICS: tuple[tuple[re.Pattern[str], dict[str, float | int]], ...] = (
    (re.compile(r"postgres", re.I), {"resource_cpu": 1.0, "resource_memory_mb": 2048, "resource_disk_gb": 20.0}),
    (re.compile(r"redis", re.I), {"resource_cpu": 0.5, "resource_memory_mb": 1024, "resource_disk_gb": 8.0}),
    (re.compile(r"nginx", re.I), {"resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5.0}),
    (re.compile(r"mysql|mariadb", re.I), {"resource_cpu": 1.0, "resource_memory_mb": 2048, "resource_disk_gb": 25.0}),
    (re.compile(r"rabbitmq|kafka", re.I), {"resource_cpu": 0.5, "resource_memory_mb": 1024, "resource_disk_gb": 10.0}),
    (re.compile(r"ubuntu", re.I), {"resource_cpu": 0.5, "resource_memory_mb": 1024, "resource_disk_gb": 10.0}),
)

_NODE_TYPE_ROLE: dict[str, str] = {
    "router": "router",
    "switch": "router",
    "gateway": "gateway",
    "host": "workload",
    "generic": "workload",
    "service": "workload",
}

_NETWORK_ONLY_TYPES = frozenset({"router", "switch"})


@dataclass(frozen=True)
class NodeResourceMetadata:
    resource_cpu: float
    resource_memory_mb: int
    resource_disk_gb: float
    replicas: int
    node_role: str
    exposure: str
    stateful: bool
    required_ports: tuple[int, ...]
    placement_constraints: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True)
class PlacementUnit:
    node_id: str
    node_name: str
    replica_index: int
    resource_cpu: float
    resource_memory_mb: int
    resource_disk_gb: float
    node_role: str
    exposure: str
    stateful: bool
    required_ports: tuple[int, ...]
    placement_constraints: tuple[str, ...]


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise NodeConfigValidationError("resource values must be numeric") from exc
    if parsed < 0:
        raise NodeConfigValidationError("resource values must be non-negative")
    return parsed


def _coerce_int(value: Any, *, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise NodeConfigValidationError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise NodeConfigValidationError(f"{name} must be non-negative")
    return parsed


def _read_resource_block(config: dict[str, Any]) -> dict[str, Any]:
    block = config.get("resources")
    if isinstance(block, dict):
        return block
    return {}


def _resolve_resource_value(config: dict[str, Any], *keys: str) -> Any:
    resources = _read_resource_block(config)
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
        if key in resources and resources[key] is not None:
            return resources[key]
    legacy = {
        "resource_cpu": ("cpu_request",),
        "resource_memory_mb": ("memory_request_mb",),
        "resource_disk_gb": ("disk_request_gb",),
    }
    for key in keys:
        for legacy_key in legacy.get(key, ()):
            if legacy_key in config and config[legacy_key] is not None:
                return config[legacy_key]
            if legacy_key in resources and resources[legacy_key] is not None:
                return resources[legacy_key]
    return None


def _infer_defaults(node: TopologyNode) -> dict[str, float | int]:
    image = (node.image or "").lower()
    for pattern, defaults in _IMAGE_HEURISTICS:
        if pattern.search(image):
            return dict(defaults)
    node_type = (node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)).lower()
    if node_type in _NETWORK_ONLY_TYPES:
        return {"resource_cpu": 0.1, "resource_memory_mb": 128, "resource_disk_gb": 1.0}
    return {
        "resource_cpu": _DEFAULT_CPU,
        "resource_memory_mb": _DEFAULT_MEMORY_MB,
        "resource_disk_gb": _DEFAULT_DISK_GB,
    }


def _infer_node_role(node: TopologyNode, config: dict[str, Any]) -> str:
    explicit = str(config.get("node_role") or "").strip().lower()
    if explicit:
        return explicit
    node_type = (node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)).lower()
    return _NODE_TYPE_ROLE.get(node_type, "workload")


def _parse_required_ports(config: dict[str, Any], runtime_ports: tuple[int, ...]) -> tuple[int, ...]:
    raw = config.get("required_ports")
    if raw is None:
        if runtime_ports:
            return runtime_ports
        exposure = str(config.get("exposure") or "internal").strip().lower()
        if exposure == "public":
            return (80, 443)
        return ()
    if not isinstance(raw, list):
        raise NodeConfigValidationError("required_ports must be a JSON array of integers")
    ports: list[int] = []
    for item in raw:
        try:
            port = int(item)
        except (TypeError, ValueError) as exc:
            raise NodeConfigValidationError("required_ports entries must be integers") from exc
        if port <= 0 or port > 65535:
            raise NodeConfigValidationError("required_ports must be between 1 and 65535")
        ports.append(port)
    return tuple(sorted(set(ports)))


def _parse_placement_constraints(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise NodeConfigValidationError("placement_constraints must be a JSON array")
    out: list[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if not key:
            continue
        if key not in SUPPORTED_PLACEMENT_CONSTRAINTS:
            raise NodeConfigValidationError(
                f"unsupported placement constraint '{key}'; "
                f"supported: {', '.join(sorted(SUPPORTED_PLACEMENT_CONSTRAINTS))}"
            )
        out.append(key)
    return tuple(out)


def extract_node_resource_metadata(node: TopologyNode) -> NodeResourceMetadata | None:
    """Return resource metadata for workload nodes; network-only nodes may be omitted."""
    node_type = (node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)).lower()
    config = dict(node.config or {})
    defaults = _infer_defaults(node)

    cpu = _coerce_float(
        _resolve_resource_value(config, "resource_cpu"),
        default=float(defaults["resource_cpu"]),
    )
    memory_mb = _coerce_int(
        _resolve_resource_value(config, "resource_memory_mb"),
        default=int(defaults["resource_memory_mb"]),
        name="resource_memory_mb",
    )
    disk_gb = _coerce_float(
        _resolve_resource_value(config, "resource_disk_gb"),
        default=float(defaults["resource_disk_gb"]),
    )
    replicas = _coerce_int(
        _resolve_resource_value(config, "replicas"),
        default=_DEFAULT_REPLICAS,
        name="replicas",
    )
    if replicas < 1:
        raise NodeConfigValidationError("replicas must be at least 1")

    if node_type in _NETWORK_ONLY_TYPES and replicas == 1 and cpu <= 0.25 and memory_mb <= 256:
        return None

    node_role = _infer_node_role(node, config)
    if node_role not in NODE_ROLES:
        raise NodeConfigValidationError(
            f"node_role must be one of: {', '.join(sorted(NODE_ROLES))}"
        )

    exposure = str(config.get("exposure") or "internal").strip().lower()
    if exposure not in EXPOSURE_VALUES:
        raise NodeConfigValidationError(
            f"exposure must be one of: {', '.join(sorted(EXPOSURE_VALUES))}"
        )

    stateful_raw = config.get("stateful")
    stateful = bool(stateful_raw) if isinstance(stateful_raw, bool) else str(stateful_raw or "").lower() in (
        "1",
        "true",
        "yes",
    )
    if node_role in {"database", "storage", "cache", "queue"}:
        stateful = stateful or True

    runtime = extract_node_runtime_config(config)
    runtime_ports = tuple(sorted({p.port for p in runtime.ports}))
    required_ports = _parse_required_ports(config, runtime_ports)
    constraints = _parse_placement_constraints(config.get("placement_constraints"))
    notes = str(config.get("notes") or config.get("description") or "").strip() or None

    return NodeResourceMetadata(
        resource_cpu=cpu,
        resource_memory_mb=memory_mb,
        resource_disk_gb=disk_gb,
        replicas=replicas,
        node_role=node_role,
        exposure=exposure,
        stateful=stateful,
        required_ports=required_ports,
        placement_constraints=constraints,
        notes=notes,
    )


def expand_placement_units(topology) -> list[PlacementUnit]:
    units: list[PlacementUnit] = []
    for node in topology.nodes or []:
        meta = extract_node_resource_metadata(node)
        if meta is None:
            continue
        node_id = str(node.id)
        for replica_index in range(meta.replicas):
            units.append(
                PlacementUnit(
                    node_id=node_id,
                    node_name=node.name,
                    replica_index=replica_index,
                    resource_cpu=meta.resource_cpu,
                    resource_memory_mb=meta.resource_memory_mb,
                    resource_disk_gb=meta.resource_disk_gb,
                    node_role=meta.node_role,
                    exposure=meta.exposure,
                    stateful=meta.stateful,
                    required_ports=meta.required_ports,
                    placement_constraints=meta.placement_constraints,
                )
            )
    return units


def validate_and_normalize_resource_metadata(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate and persist canonical resource_* keys on node config."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise NodeConfigValidationError("config must be a JSON object")

    out = dict(config)
    _coerce_float(_resolve_resource_value(out, "resource_cpu"), default=_DEFAULT_CPU)
    _coerce_int(
        _resolve_resource_value(out, "resource_memory_mb"),
        default=_DEFAULT_MEMORY_MB,
        name="resource_memory_mb",
    )
    disk_gb = _coerce_float(
        _resolve_resource_value(out, "resource_disk_gb"),
        default=_DEFAULT_DISK_GB,
    )
    replicas = _coerce_int(
        _resolve_resource_value(out, "replicas"),
        default=_DEFAULT_REPLICAS,
        name="replicas",
    )
    if replicas < 1:
        raise NodeConfigValidationError("replicas must be at least 1")

    node_role = str(out.get("node_role") or "").strip().lower()
    if node_role and node_role not in NODE_ROLES:
        raise NodeConfigValidationError(
            f"node_role must be one of: {', '.join(sorted(NODE_ROLES))}"
        )
    if node_role:
        out["node_role"] = node_role

    exposure = str(out.get("exposure") or "").strip().lower()
    if exposure and exposure not in EXPOSURE_VALUES:
        raise NodeConfigValidationError(
            f"exposure must be one of: {', '.join(sorted(EXPOSURE_VALUES))}"
        )
    if exposure:
        out["exposure"] = exposure

    _parse_placement_constraints(out.get("placement_constraints"))
    runtime = extract_node_runtime_config(out)
    runtime_ports = tuple(sorted({p.port for p in runtime.ports}))
    _parse_required_ports(out, runtime_ports)

    notes = out.get("notes") or out.get("description")
    if notes is not None and len(str(notes)) > 4096:
        raise NodeConfigValidationError("notes must be at most 4096 characters")

    return out or None
