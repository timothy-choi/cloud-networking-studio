"""Structured diff between topology version snapshots (Step 56)."""

from __future__ import annotations

import copy
from typing import Any

from app.core.secret_masking import scrub_sensitive_dict


def _index_by_id(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items}


def _node_key_fields(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": node.get("name"),
        "node_type": node.get("node_type"),
        "image": node.get("image"),
        "ip_address": node.get("ip_address"),
        "config": node.get("config"),
    }


def _link_key_fields(link: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_node_id": link.get("source_node_id"),
        "target_node_id": link.get("target_node_id"),
        "network_name": link.get("network_name"),
        "cidr": link.get("cidr"),
        "gateway": link.get("gateway"),
        "vlan_tag": link.get("vlan_tag"),
        "source_endpoint_ip": link.get("source_endpoint_ip"),
        "target_endpoint_ip": link.get("target_endpoint_ip"),
        "config": link.get("config"),
    }


def _extract_ports(config: dict[str, Any] | None) -> list[Any]:
    if not config:
        return []
    ports = config.get("ports") or config.get("services") or []
    return copy.deepcopy(ports) if isinstance(ports, list) else []


def _extract_env(config: dict[str, Any] | None) -> dict[str, str]:
    if not config:
        return {}
    env = config.get("env")
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    return {}


def _extract_health(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return None
    hc = config.get("health_check") or config.get("healthCheck")
    return copy.deepcopy(hc) if isinstance(hc, dict) else None


def _diff_dicts(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any] | None:
    l = left or {}
    r = right or {}
    if l == r:
        return None
    return {"before": scrub_sensitive_dict(l), "after": scrub_sensitive_dict(r)}


def diff_topology_snapshots(
    left_snapshot: dict[str, Any],
    right_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Compare two snapshots; ``left`` is older/base, ``right`` is newer/target."""
    left_nodes = _index_by_id(left_snapshot.get("nodes") or [])
    right_nodes = _index_by_id(right_snapshot.get("nodes") or [])
    left_links = _index_by_id(left_snapshot.get("links") or [])
    right_links = _index_by_id(right_snapshot.get("links") or [])

    nodes_added = [
        scrub_sensitive_dict(_node_key_fields(n))
        for nid, n in right_nodes.items()
        if nid not in left_nodes
    ]
    nodes_removed = [
        scrub_sensitive_dict(_node_key_fields(n))
        for nid, n in left_nodes.items()
        if nid not in right_nodes
    ]
    nodes_changed: list[dict[str, Any]] = []
    for nid in left_nodes.keys() & right_nodes.keys():
        before = _node_key_fields(left_nodes[nid])
        after = _node_key_fields(right_nodes[nid])
        if before != after:
            nodes_changed.append(
                {
                    "id": nid,
                    "name": after.get("name") or before.get("name"),
                    "changes": _diff_dicts(before, after),
                }
            )

    links_added = [
        scrub_sensitive_dict(_link_key_fields(lnk))
        for lid, lnk in right_links.items()
        if lid not in left_links
    ]
    links_removed = [
        scrub_sensitive_dict(_link_key_fields(lnk))
        for lid, lnk in left_links.items()
        if lid not in right_links
    ]
    links_changed: list[dict[str, Any]] = []
    for lid in left_links.keys() & right_links.keys():
        before = _link_key_fields(left_links[lid])
        after = _link_key_fields(right_links[lid])
        if before != after:
            links_changed.append(
                {
                    "id": lid,
                    "network_name": after.get("network_name") or before.get("network_name"),
                    "changes": _diff_dicts(before, after),
                }
            )

    services_changed: list[dict[str, Any]] = []
    env_changed: dict[str, Any] = {}
    health_changed: list[dict[str, Any]] = []

    all_node_ids = left_nodes.keys() | right_nodes.keys()
    for nid in all_node_ids:
        ln = left_nodes.get(nid, {})
        rn = right_nodes.get(nid, {})
        lcfg = ln.get("config") or {}
        rcfg = rn.get("config") or {}
        name = rn.get("name") or ln.get("name") or nid

        lports = _extract_ports(lcfg)
        rports = _extract_ports(rcfg)
        if lports != rports:
            services_changed.append(
                {
                    "node_id": nid,
                    "node_name": name,
                    "before": lports,
                    "after": rports,
                }
            )

        lenv = _extract_env(lcfg)
        renv = _extract_env(rcfg)
        if lenv != renv:
            added = {k: scrub_sensitive_dict({k: v})[k] for k in renv.keys() - lenv.keys()}
            removed = list(lenv.keys() - renv.keys())
            changed = {}
            for k in lenv.keys() & renv.keys():
                if lenv[k] != renv[k]:
                    changed[k] = {
                        "before": scrub_sensitive_dict({k: lenv[k]})[k],
                        "after": scrub_sensitive_dict({k: renv[k]})[k],
                    }
            if added or removed or changed:
                env_changed[name] = {
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                }

        lhc = _extract_health(lcfg)
        rhc = _extract_health(rcfg)
        if lhc != rhc:
            health_changed.append(
                {
                    "node_id": nid,
                    "node_name": name,
                    "before": scrub_sensitive_dict(lhc),
                    "after": scrub_sensitive_dict(rhc),
                }
            )

    left_topo = left_snapshot.get("topology") or {}
    right_topo = right_snapshot.get("topology") or {}
    runtime_fields = (
        "runtime_target",
        "networking_mode",
        "status",
        "config",
    )
    runtime_before = {k: left_topo.get(k) for k in runtime_fields if k in left_topo}
    runtime_after = {k: right_topo.get(k) for k in runtime_fields if k in right_topo}
    runtime_metadata_changed = None
    if runtime_before != runtime_after:
        runtime_metadata_changed = {
            "before": scrub_sensitive_dict(runtime_before),
            "after": scrub_sensitive_dict(runtime_after),
        }

    return {
        "nodes": {
            "added": nodes_added,
            "removed": nodes_removed,
            "changed": nodes_changed,
        },
        "links": {
            "added": links_added,
            "removed": links_removed,
            "changed": links_changed,
        },
        "services": {"changed": services_changed},
        "env_vars": env_changed,
        "health_checks": {"changed": health_changed},
        "runtime_metadata": runtime_metadata_changed,
    }
