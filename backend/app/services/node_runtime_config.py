"""Extract optional freeform runtime settings from topology node ``config`` JSON."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any

_IMAGE_REF_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/@:+-]{0,511}$")
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_MAX_COMMAND_LEN = 4096
_MAX_ENV_VALUE_LEN = 8192
_MAX_ENV_ENTRIES = 64
_MAX_PORTS = 16


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
    kubernetes_service_type: str | None = None


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
        kubernetes_service_type=_coerce_str(config.get("kubernetes_service_type")),
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


class NodeConfigValidationError(ValueError):
    """Raised when freeform node config fails API validation."""


_HEALTH_CHECK_TYPES = frozenset({"runtime", "tcp", "http", "command", "none"})


def _infer_default_check_type(
    image: str | None,
    primary_port: int,
    *,
    has_explicit_ports: bool = False,
) -> str:
    il = (image or "").lower()
    if "nginx" in il or "httpd" in il:
        return "http"
    if "redis" in il:
        return "tcp"
    if "postgres" in il:
        return "tcp"
    if has_explicit_ports and primary_port in (80, 443, 8080):
        return "http"
    return "runtime"


def normalize_health_check(
    raw: dict[str, Any] | None,
    *,
    image: str | None = None,
    primary_port: int = 80,
    has_explicit_ports: bool = False,
) -> dict[str, Any] | None:
    """Resolve health_check dict with explicit or inferred check_type."""
    if raw is None:
        check_type = _infer_default_check_type(
            image, primary_port, has_explicit_ports=has_explicit_ports
        )
        if check_type == "http":
            return {
                "check_type": "http",
                "port": primary_port if primary_port > 0 else 80,
                "path": "/",
            }
        if check_type == "tcp":
            il = (image or "").lower()
            port = 6379 if "redis" in il else 5432 if "postgres" in il else primary_port
            return {"check_type": "tcp", "port": port}
        return {"check_type": check_type}
    hc = dict(raw)
    if "path" in hc and isinstance(hc["path"], str) and hc["path"] and "check_type" not in hc:
        hc.setdefault("check_type", "http")
    check_type = str(hc.get("check_type") or "").strip().lower()
    if not check_type:
        if _parse_command(hc.get("command")):
            check_type = "command"
        elif hc.get("path"):
            check_type = "http"
        elif hc.get("port") is not None:
            check_type = "tcp"
        else:
            check_type = _infer_default_check_type(
                image, primary_port, has_explicit_ports=has_explicit_ports
            )
    if check_type not in _HEALTH_CHECK_TYPES:
        raise NodeConfigValidationError(
            f"health_check.check_type must be one of: {', '.join(sorted(_HEALTH_CHECK_TYPES))}"
        )
    hc["check_type"] = check_type
    if check_type == "http":
        hc.setdefault("path", "/")
        if hc.get("port") is None:
            hc["port"] = primary_port if primary_port > 0 else 80
    if check_type == "tcp" and hc.get("port") is None:
        il = (image or "").lower()
        if "redis" in il:
            hc["port"] = 6379
        elif "postgres" in il:
            hc["port"] = 5432
        else:
            hc["port"] = primary_port if primary_port > 0 else 80
    if check_type == "command":
        cmd = _parse_command(hc.get("command"))
        if not cmd:
            raise NodeConfigValidationError("health_check.command is required for command checks")
        hc["command"] = cmd
    return hc


def health_probe_payload_for_node(
    *,
    image: str | None,
    runtime: NodeRuntimeConfig,
) -> dict[str, Any]:
    """Build Go runner health-check request body from persisted node intent."""
    primary = primary_port(runtime) if runtime.ports else 0
    hc = normalize_health_check(
        runtime.health_check,
        image=image,
        primary_port=primary if primary > 0 else 80,
        has_explicit_ports=bool(runtime.ports),
    )
    if hc is None:
        hc = {"check_type": "runtime"}
    payload: dict[str, Any] = {
        "check_type": hc.get("check_type", "runtime"),
        "image": (image or "").strip(),
        "primary_port": primary,
    }
    if hc.get("port") is not None:
        payload["port"] = int(hc["port"])
    if hc.get("path"):
        payload["path"] = str(hc["path"])
    if hc.get("command"):
        payload["command"] = hc["command"]
    if hc.get("expected_status") is not None:
        payload["expected_status"] = int(hc["expected_status"])
    if hc.get("timeout_ms") is not None:
        payload["timeout_ms"] = int(hc["timeout_ms"])
    return payload


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
        hc = normalize_health_check(
            runtime.health_check,
            image=image,
            primary_port=primary_port(runtime) if runtime.ports else 0,
            has_explicit_ports=bool(runtime.ports),
        )
        if hc:
            meta["health_check_type"] = str(hc.get("check_type", "runtime"))
            path = hc.get("path")
            if path is not None:
                meta["health_check_path"] = str(path)
            port = hc.get("port")
            if port is not None:
                meta["health_check_port"] = str(port)
    if ip_address and str(ip_address).strip():
        meta["intended_ip"] = str(ip_address).strip()
    if runtime.env:
        meta["env"] = json.dumps(runtime.env, sort_keys=True)
    return meta


def validate_image_reference(image: str | None) -> str | None:
    if image is None:
        return None
    s = str(image).strip()
    if not s:
        return None
    if len(s) > 512:
        raise NodeConfigValidationError("image must be at most 512 characters")
    if not _IMAGE_REF_PATTERN.match(s):
        raise NodeConfigValidationError(
            "image contains invalid characters; use a standard container reference "
            "(e.g. nginx:alpine, ghcr.io/org/app:1.2)"
        )
    return s


def validate_intent_ip(ip_address: str | None) -> str | None:
    if ip_address is None:
        return None
    s = str(ip_address).strip()
    if not s:
        return None
    if len(s) > 64:
        raise NodeConfigValidationError("ip_address must be at most 64 characters")
    return s


def _validate_ports_raw(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        raise NodeConfigValidationError("ports must be a JSON array")
    if len(raw) > _MAX_PORTS:
        raise NodeConfigValidationError(f"ports supports at most {_MAX_PORTS} entries")
    for item in raw:
        if isinstance(item, int):
            if item <= 0 or item > 65535:
                raise NodeConfigValidationError("port numbers must be between 1 and 65535")
            continue
        if not isinstance(item, dict):
            raise NodeConfigValidationError("each port entry must be a number or object with port")
        port_raw = item.get("port")
        try:
            port = int(port_raw)
        except (TypeError, ValueError) as exc:
            raise NodeConfigValidationError("port must be an integer") from exc
        if port <= 0 or port > 65535:
            raise NodeConfigValidationError("port numbers must be between 1 and 65535")
        tp_raw = item.get("target_port", port)
        if tp_raw is not None:
            try:
                tp = int(tp_raw)
            except (TypeError, ValueError) as exc:
                raise NodeConfigValidationError("target_port must be an integer") from exc
            if tp <= 0 or tp > 65535:
                raise NodeConfigValidationError("target_port must be between 1 and 65535")


def _validate_env_raw(raw: Any) -> None:
    if raw is None:
        return
    if isinstance(raw, list):
        if len(raw) > _MAX_ENV_ENTRIES:
            raise NodeConfigValidationError(f"env supports at most {_MAX_ENV_ENTRIES} entries")
        for item in raw:
            if not isinstance(item, str) or "=" not in item:
                raise NodeConfigValidationError("env list entries must be KEY=value strings")
            key, _, val = item.partition("=")
            key = key.strip()
            if not key or not _ENV_KEY_PATTERN.match(key):
                raise NodeConfigValidationError(f"invalid env key: {key!r}")
            if len(val) > _MAX_ENV_VALUE_LEN:
                raise NodeConfigValidationError("env values must be at most 8192 characters")
        return
    if isinstance(raw, dict):
        if len(raw) > _MAX_ENV_ENTRIES:
            raise NodeConfigValidationError(f"env supports at most {_MAX_ENV_ENTRIES} entries")
        for key, val in raw.items():
            k = str(key).strip()
            if not k or not _ENV_KEY_PATTERN.match(k):
                raise NodeConfigValidationError(f"invalid env key: {k!r}")
            if len(str(val)) > _MAX_ENV_VALUE_LEN:
                raise NodeConfigValidationError("env values must be at most 8192 characters")
        return
    raise NodeConfigValidationError("env must be a JSON object or array of KEY=value strings")


def validate_and_normalize_node_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate freeform keys in node config; normalize parsed ports/env/command."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise NodeConfigValidationError("config must be a JSON object")

    out = dict(config)
    cmd_raw = out.get("command")
    if cmd_raw is not None:
        if isinstance(cmd_raw, str) and len(cmd_raw) > _MAX_COMMAND_LEN:
            raise NodeConfigValidationError("command must be at most 4096 characters")
        if isinstance(cmd_raw, list):
            joined = " ".join(str(x) for x in cmd_raw)
            if len(joined) > _MAX_COMMAND_LEN:
                raise NodeConfigValidationError("command must be at most 4096 characters")

    _validate_ports_raw(out.get("ports"))
    _validate_env_raw(out.get("env"))

    role = out.get("role_label")
    if role is not None and len(str(role).strip()) > 128:
        raise NodeConfigValidationError("role_label must be at most 128 characters")

    desc = out.get("description") or out.get("notes")
    if desc is not None and len(str(desc)) > 4096:
        raise NodeConfigValidationError("description must be at most 4096 characters")

    parsed = extract_node_runtime_config(out)
    if parsed.command:
        out["command"] = parsed.command
    if parsed.ports:
        out["ports"] = [
            {
                "port": p.port,
                "target_port": p.target_port or p.port,
                "protocol": p.protocol,
            }
            for p in parsed.ports
        ]
    if parsed.env:
        out["env"] = parsed.env
    return out or None


def validate_node_payload(
    *,
    image: str | None,
    ip_address: str | None,
    config: dict[str, Any] | None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Validate node create/update fields; returns normalized values."""
    img = validate_image_reference(image)
    ip = validate_intent_ip(ip_address)
    cfg = validate_and_normalize_node_config(config)
    if cfg is not None:
        parsed = extract_node_runtime_config(cfg)
        cfg["health_check"] = normalize_health_check(
            parsed.health_check,
            image=img,
            primary_port=primary_port(parsed) if parsed.ports else 0,
            has_explicit_ports=bool(parsed.ports),
        )
    return img, ip, cfg
