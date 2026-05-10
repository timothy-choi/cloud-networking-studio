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
class DeploymentPlan:
    """Immutable snapshot of intent sent to a runtime provider."""

    topology_id: UUID
    runtime_target: str
    networking_mode: str
    steps: tuple[str, ...]
    node_names: tuple[str, ...]
    links: tuple[tuple[str, str, str], ...]
    """Each entry is (source_node_name, target_node_name, network_name)."""


def build_deployment_plan(topology: Topology) -> DeploymentPlan:
    """
    Produce a provider-neutral plan from ORM state.

    Expects ``topology.nodes`` and ``topology.links`` to be pre-loaded.
    """
    node_by_id = {n.id: n for n in topology.nodes}

    links: list[tuple[str, str, str]] = []
    for link in topology.links:
        src = node_by_id.get(link.source_node_id)
        tgt = node_by_id.get(link.target_node_id)
        if src is None or tgt is None:
            continue
        links.append((src.name, tgt.name, link.network_name))

    node_names = tuple(sorted({n.name for n in topology.nodes}, key=lambda x: x))

    return DeploymentPlan(
        topology_id=topology.id,
        runtime_target=topology.runtime_target,
        networking_mode=topology.networking_mode,
        steps=DEFAULT_PLAN_STEPS,
        node_names=node_names,
        links=tuple(links),
    )
