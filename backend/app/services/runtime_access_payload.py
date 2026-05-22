"""Build ``runtime_access`` payloads for control-plane persistence (Docker executor)."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import docker
from docker.errors import NotFound

from app.services.deployment_planner import DeploymentPlan
from app.services.node_runtime_config import (
    NodeRuntimeConfig,
    primary_port,
    runtime_access_ports_payload,
    runtime_metadata_from_node,
)


def topology_network_name(topology_id: UUID) -> str:
    short = str(topology_id).replace("-", "")[:12]
    return f"cns-topology-{short}"


def segment_docker_network_name(topology_id: UUID, logical_network_name: str) -> str:
    short = str(topology_id).replace("-", "")[:12]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", logical_network_name.strip().lower()).strip("-")[:22]
    slug = slug or "seg"
    return f"cns-sg-{short}-{slug}"[:63]


def _plan_node_runtime(pn) -> NodeRuntimeConfig:
    rc = getattr(pn, "runtime_config", None)
    if isinstance(rc, NodeRuntimeConfig):
        return rc
    return NodeRuntimeConfig()


def _resource_row_for_plan_node(
    pn,
    *,
    net: str,
    meta: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build node + service runtime_access rows for one plan node."""
    runtime = _plan_node_runtime(pn)
    port = primary_port(runtime)
    cname = container_name(pn.id, pn.name)
    internal = f"http://{cname}:{port}"
    ports = runtime_access_ports_payload(runtime)
    row_meta = {
        **runtime_metadata_from_node(
            image=pn.image,
            ip_address=pn.ip_address,
            runtime=runtime,
        ),
        **meta,
    }
    nid = str(pn.id)
    row_base: dict[str, Any] = {
        "name": pn.name,
        "runtime_name": cname,
        "status": "running",
        "namespace_or_network": net,
        "internal_url": internal,
        "ports": ports,
        "metadata": row_meta,
    }
    node_row = {"type": "node", "node_id": nid, **row_base}
    service_row = {"type": "service", "service_id": nid, **row_base}
    return node_row, service_row


def container_name(node_id: UUID, node_name: str) -> str:
    short_id = str(node_id).replace("-", "")[:12]
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", node_name).strip("-")[:40] or "node"
    return f"cns-node-{short_id}-{safe}"


def _container_ipv4_on_network(attrs: dict[str, Any], net_name: str) -> str | None:
    nets = (attrs.get("NetworkSettings") or {}).get("Networks") or {}
    ent = nets.get(net_name) or {}
    ip = ent.get("IPAddress")
    return str(ip).strip() if ip else None


def build_docker_runtime_access_from_plan(
    client: docker.DockerClient,
    plan: DeploymentPlan,
) -> dict[str, Any]:
    """
    Synthesize runner-shaped ``runtime_access`` after a successful in-process Docker deploy.

    Does not require static IPs; ``intended_ip`` is set from the plan when present and
    ``actual_runtime_ip`` from container inspect when available.
    """
    if plan.deployment_id is None or plan.topology_id is None:
        return {}

    topo_id = plan.topology_id
    dep_id = plan.deployment_id
    primary_net = topology_network_name(topo_id)
    resources: list[dict[str, Any]] = []

    node_net: dict[UUID, str] = {}

    if plan.segmented_networks:
        seen_logical: set[str] = set()
        for pl in plan.plan_links:
            key = pl.network_name.strip().lower()
            if key in seen_logical:
                continue
            seen_logical.add(key)
            dnet = segment_docker_network_name(topo_id, pl.network_name)
            resources.append(
                {
                    "type": "network",
                    "name": pl.network_name,
                    "runtime_name": dnet,
                    "status": "active",
                    "namespace_or_network": dnet,
                    "metadata": {
                        "topology_id": str(topo_id),
                        "logical_network": pl.network_name,
                    },
                }
            )
        logical_to_docker = {
            pl.network_name.strip().lower(): segment_docker_network_name(topo_id, pl.network_name)
            for pl in plan.plan_links
        }
        for pl in plan.plan_links:
            dnet = logical_to_docker[pl.network_name.strip().lower()]
            node_net.setdefault(pl.source_node_id, dnet)
            node_net.setdefault(pl.target_node_id, dnet)
    else:
        resources.append(
            {
                "type": "network",
                "name": primary_net,
                "runtime_name": primary_net,
                "status": "active",
                "namespace_or_network": primary_net,
                "metadata": {"topology_id": str(topo_id)},
            }
        )
        for pn in plan.nodes:
            node_net[pn.id] = primary_net

    for pn in plan.nodes:
        net = node_net.get(pn.id, primary_net)
        meta: dict[str, str] = {"topology_id": str(topo_id)}
        try:
            cname = container_name(pn.id, pn.name)
            ctr = client.containers.get(cname)
            ctr.reload()
            meta["container_id"] = (ctr.id or "")[:64]
            actual = _container_ipv4_on_network(ctr.attrs, net)
            if actual:
                meta["actual_runtime_ip"] = actual
        except NotFound:
            pass
        node_row, service_row = _resource_row_for_plan_node(pn, net=net, meta=meta)
        resources.append(node_row)
        resources.append(service_row)

    ns_net = primary_net
    if plan.segmented_networks and plan.nodes:
        ns_net = node_net.get(plan.nodes[0].id, primary_net)

    return {
        "deployment_id": str(dep_id),
        "topology_id": str(topo_id),
        "status": "running",
        "runtime_provider": "docker",
        "namespace_or_network": ns_net,
        "resources": resources,
    }


def build_fake_runtime_access_from_plan(plan: DeploymentPlan) -> dict[str, Any]:
    """Minimal registry rows for simulated deploys (no Docker socket)."""
    if plan.deployment_id is None or plan.topology_id is None:
        return {}
    topo_id = plan.topology_id
    dep_id = plan.deployment_id
    net = topology_network_name(topo_id)
    resources: list[dict[str, Any]] = [
        {
            "type": "network",
            "name": net,
            "runtime_name": net,
            "status": "active",
            "namespace_or_network": net,
            "metadata": {"topology_id": str(topo_id), "simulated": "true"},
        }
    ]
    for pn in plan.nodes:
        meta: dict[str, str] = {"topology_id": str(topo_id), "simulated": "true"}
        if pn.ip_address and str(pn.ip_address).strip():
            meta["actual_runtime_ip"] = str(pn.ip_address).strip()
        node_row, service_row = _resource_row_for_plan_node(pn, net=net, meta=meta)
        resources.append(node_row)
        resources.append(service_row)
    return {
        "deployment_id": str(dep_id),
        "topology_id": str(topo_id),
        "status": "running",
        "runtime_provider": "docker",
        "namespace_or_network": net,
        "resources": resources,
    }
