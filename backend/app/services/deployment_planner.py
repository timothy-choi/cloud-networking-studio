"""Build a structured deployment plan from a persisted topology graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.topology import Topology

# Ordered orchestration phases — providers map these to concrete actions later.
DEFAULT_PLAN_STEPS: tuple[str, ...] = (
    "validate_topology",
    "select_runtime_provider",
    "create_virtual_networks",
    "create_runtime_nodes",
    "attach_nodes_to_networks",
    "run_health_checks",
    "mark_deployment_ready",
)


@dataclass(frozen=True)
class PlanNode:
    """One vertex to materialize at runtime."""

    id: UUID
    name: str
    image: str | None
    ip_address: str | None


@dataclass(frozen=True)
class DeploymentPlan:
    """Immutable snapshot of intent sent to a runtime provider."""

    topology_id: UUID
    runtime_target: str
    networking_mode: str
    steps: tuple[str, ...]
    nodes: tuple[PlanNode, ...]
    node_names: tuple[str, ...]
    links: tuple[tuple[str, str, str], ...]
    """Each entry is (source_node_name, target_node_name, network_name)."""
    subnet_cidr: str | None
    """Preferred Docker IPAM subnet from the first link that declares a CIDR."""


def build_deployment_plan(topology: Topology) -> DeploymentPlan:
    """
    Produce a provider-neutral plan from ORM state.

    Expects ``topology.nodes`` and ``topology.links`` to be pre-loaded.
    """
    node_by_id = {n.id: n for n in topology.nodes}

    links: list[tuple[str, str, str]] = []
    subnet_cidr: str | None = None
    for link in topology.links:
        if subnet_cidr is None and link.cidr:
            subnet_cidr = link.cidr
        src = node_by_id.get(link.source_node_id)
        tgt = node_by_id.get(link.target_node_id)
        if src is None or tgt is None:
            continue
        links.append((src.name, tgt.name, link.network_name))

    plan_nodes = tuple(
        PlanNode(id=n.id, name=n.name, image=n.image, ip_address=n.ip_address)
        for n in sorted(topology.nodes, key=lambda x: x.name)
    )
    node_names = tuple(n.name for n in plan_nodes)

    return DeploymentPlan(
        topology_id=topology.id,
        runtime_target=topology.runtime_target,
        networking_mode=topology.networking_mode,
        steps=DEFAULT_PLAN_STEPS,
        nodes=plan_nodes,
        node_names=node_names,
        links=tuple(links),
        subnet_cidr=subnet_cidr,
    )
