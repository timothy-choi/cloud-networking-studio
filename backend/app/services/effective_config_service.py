"""Resolve effective deploy config from topology + profile overrides (Step 56)."""

from __future__ import annotations

import copy
import re
from typing import Any

from app.core.secret_masking import scrub_sensitive_dict
from app.models.deployment_profile import DeploymentProfile
from app.models.topology import Topology
from app.services.topology_version_service import build_topology_snapshot


def _apply_image_tag_override(image: str | None, tag_override: str) -> str | None:
    if not tag_override:
        return image
    tag_override = tag_override.strip()
    if not tag_override:
        return image
    if "/" in tag_override or ":" in tag_override or tag_override.startswith("@"):
        return tag_override
    if not image:
        return tag_override
    base = image.split("@")[0]
    if ":" in base.rsplit("/", 1)[-1]:
        base = re.sub(r":[^:/@]+$", "", base)
    return f"{base}:{tag_override}"


def build_effective_config(
    topology: Topology | None = None,
    profile: DeploymentProfile | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
    network_allocation_mode: str | None = None,
) -> dict[str, Any]:
    """Merge topology snapshot with profile overrides without mutating ORM."""
    if snapshot is not None:
        base = copy.deepcopy(snapshot)
    elif topology is not None:
        base = build_topology_snapshot(topology)
    else:
        raise ValueError("topology or snapshot required")
    effective = copy.deepcopy(base)

    if network_allocation_mode:
        topo_cfg = effective.setdefault("topology", {}).setdefault("config", {}) or {}
        if not isinstance(topo_cfg, dict):
            topo_cfg = {}
            effective["topology"]["config"] = topo_cfg
        topo_cfg["network_allocation_mode"] = network_allocation_mode

    if profile is None:
        return effective

    pcfg = profile.config_json or {}
    env_overrides: dict[str, dict[str, str]] = pcfg.get("env_overrides") or {}
    image_overrides: dict[str, str] = pcfg.get("image_tag_overrides") or {}
    replica_hints: dict[str, Any] = pcfg.get("replica_hints") or {}
    resource_limits: dict[str, Any] = pcfg.get("resource_limits") or {}

    nodes_by_name = {n["name"]: n for n in effective.get("nodes") or []}

    for node_name, env_patch in env_overrides.items():
        node = nodes_by_name.get(node_name)
        if node is None:
            continue
        cfg = node.setdefault("config", {}) or {}
        if not isinstance(cfg, dict):
            cfg = {}
            node["config"] = cfg
        env = dict(cfg.get("env") or {})
        env.update({str(k): str(v) for k, v in (env_patch or {}).items()})
        cfg["env"] = env

    for node_name, tag in image_overrides.items():
        node = nodes_by_name.get(node_name)
        if node is None:
            continue
        node["image"] = _apply_image_tag_override(node.get("image"), tag)

    for node_name, hint in replica_hints.items():
        node = nodes_by_name.get(node_name)
        if node is None:
            continue
        cfg = node.setdefault("config", {}) or {}
        if isinstance(cfg, dict):
            cfg["replicas"] = hint

    for node_name, limits in resource_limits.items():
        node = nodes_by_name.get(node_name)
        if node is None:
            continue
        cfg = node.setdefault("config", {}) or {}
        if isinstance(cfg, dict):
            cfg["resources"] = limits

    effective["profile"] = {
        "id": str(profile.id),
        "name": profile.name,
        "profile_type": profile.profile_type,
        "expose_policy": pcfg.get("expose_policy"),
        "health_check_strictness": pcfg.get("health_check_strictness"),
        "runtime_provider_preference": pcfg.get("runtime_provider_preference"),
        "debug_toolbox_enabled": pcfg.get("debug_toolbox_enabled"),
        "ttl_hours": pcfg.get("ttl_hours"),
        "cleanup_policy": pcfg.get("cleanup_policy"),
        "quota_limits": pcfg.get("quota_limits"),
    }

    if pref := pcfg.get("runtime_provider_preference"):
        effective["topology"]["runtime_target"] = pref

    return effective


def effective_config_summary(effective: dict[str, Any]) -> dict[str, Any]:
    """Public-safe summary for deploy preview UI."""
    profile = effective.get("profile") or {}
    nodes = effective.get("nodes") or []
    exposed: list[str] = []
    for n in nodes:
        cfg = n.get("config") or {}
        ports = cfg.get("ports") or []
        if ports:
            exposed.append(n.get("name") or "?")
    return scrub_sensitive_dict(
        {
            "node_count": len(nodes),
            "link_count": len(effective.get("links") or []),
            "runtime_target": (effective.get("topology") or {}).get("runtime_target"),
            "profile_name": profile.get("name"),
            "profile_type": profile.get("profile_type"),
            "expose_policy": profile.get("expose_policy"),
            "ttl_hours": profile.get("ttl_hours"),
            "cleanup_policy": profile.get("cleanup_policy"),
            "exposed_services": exposed,
            "debug_toolbox_enabled": profile.get("debug_toolbox_enabled"),
            "health_check_strictness": profile.get("health_check_strictness"),
        }
    ) or {}
