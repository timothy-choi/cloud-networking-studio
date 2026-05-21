"""Extract optional freeform runtime settings from topology node ``config`` JSON."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodePortSpec:
    port: int
    target_port: int | None = None
    protocol: str = "TCP"


@dataclass(frozen=True)
class NodeRuntimeConfig:
    """Runtime-facing options stored in ``TopologyNode.config`` (backward compatible)."""

    role_label: str | None = None
    command: list[str] | None = None
    ports: tuple[NodePortSpec, ...] = ()
    env: dict[str, str] | None = None
    terminal_enabled: bool | None = None
    health_check: dict[str, Any] | None = None
    description: str | None = None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_command(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
        return parts or None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        return shlex.split(s)
    return None


def _parse_env(raw: Any) -> dict[str, str] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        out: dict[str, str] = {}
        for k, v in raw.items():
            key = str(k).strip()
            if not key:
                continue
            out[key] = str(v)
        return out or None
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if not s or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            if k:
                out[k] = v
        return out or None
    return None


def _parse_ports(raw: Any) -> tuple[NodePortSpec, ...]:
    if raw is None:
        return ()
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    else:
        return ()
    specs: list[NodePortSpec] = []
    for item in items:
        if isinstance(item, int):
            if item > 0:
                specs.append(NodePortSpec(port=item, target_port=item))
            continue
        if not isinstance(item, dict):
            continue
        port_raw = item.get("port")
        if port_raw is None:
            continue
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            continue
        if port <= 0:
            continue
        tp_raw = item.get("target_port", port)
        try:
            target_port = int(tp_raw) if tp_raw is not None else port
        except (TypeError, ValueError):
            target_port = port
        protocol = _coerce_str(item.get("protocol")) or "TCP"
        specs.append(NodePortSpec(port=port, target_port=target_port, protocol=protocol.upper()))
    return tuple(specs)


def _parse_health_check(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        return {"path": s} if s else None
    if isinstance(raw, dict):
        return dict(raw) if raw else None
    return None


def _parse_terminal_enabled(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return None


def extract_node_runtime_config(config: dict[str, Any] | None) -> NodeRuntimeConfig:
    """Read well-known keys from node ``config`` without disturbing layout/editor keys."""
    if not config:
        return NodeRuntimeConfig()
    desc = _coerce_str(config.get("description") or config.get("notes"))
    return NodeRuntimeConfig(
        role_label=_coerce_str(config.get("role_label")),
        command=_parse_command(config.get("command")),
        ports=_parse_ports(config.get("ports")),
        env=_parse_env(config.get("env")),
        terminal_enabled=_parse_terminal_enabled(config.get("terminal_enabled")),
        health_check=_parse_health_check(config.get("health_check")),
        description=desc,
    )


def default_ports_for_runtime() -> tuple[NodePortSpec, ...]:
    return (NodePortSpec(port=80, target_port=80, protocol="TCP"),)


def resolve_effective_ports(runtime: NodeRuntimeConfig) -> tuple[NodePortSpec, ...]:
    return runtime.ports if runtime.ports else default_ports_for_runtime()


def primary_port(runtime: NodeRuntimeConfig) -> int:
    ports = resolve_effective_ports(runtime)
    return ports[0].port


def runtime_access_ports_payload(runtime: NodeRuntimeConfig) -> list[dict[str, Any]]:
    return [
        {
            "port": p.port,
            "target_port": p.target_port or p.port,
            "protocol": p.protocol,
        }
        for p in resolve_effective_ports(runtime)
    ]


def runtime_metadata_from_node(
    *,
    image: str | None,
    ip_address: str | None,
    runtime: NodeRuntimeConfig,
    command: list[str] | None = None,
) -> dict[str, str]:
    """Metadata keys surfaced in Runtime Access (string values only)."""
    meta: dict[str, str] = {}
    if runtime.role_label:
        meta["role_label"] = runtime.role_label
    img = (image or "").strip()
    if img:
        meta["image"] = img
    if command:
        meta["command"] = " ".join(command)
    elif runtime.command:
        meta["command"] = " ".join(runtime.command)
    if runtime.description:
        meta["description"] = runtime.description
    if runtime.terminal_enabled is not None:
        meta["terminal_enabled"] = "true" if runtime.terminal_enabled else "false"
    if runtime.health_check:
        path = runtime.health_check.get("path")
        if path is not None:
            meta["health_check_path"] = str(path)
        port = runtime.health_check.get("port")
        if port is not None:
            meta["health_check_port"] = str(port)
    if ip_address and str(ip_address).strip():
        meta["intended_ip"] = str(ip_address).strip()
    return meta
