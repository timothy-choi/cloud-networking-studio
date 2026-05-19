"""Build a structured deployment plan from a persisted topology graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.topology import NodeType, Topology
from app.services.network_allocation import (
    DEFAULT_NETWORK_ALLOCATION_MODE,
    resolve_network_allocation_mode,
)
from app.services.segmented_topology import topology_is_segmented_multinet

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
    node_type: str


@dataclass(frozen=True)
class PlanLinkDetail:
    """One L2 segment (Docker bridge) between two nodes."""

    link_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    source_name: str
    target_name: str
    network_name: str
    cidr: str | None
    gateway: str | None
    vlan_tag: int | None
    source_ip: str | None
    target_ip: str | None


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
    plan_links: tuple[PlanLinkDetail, ...]
    segmented_networks: bool
    subnet_cidr: str | None
    """Preferred Docker IPAM subnet from the first link that declares a CIDR (legacy path)."""
    network_allocation_mode: str = DEFAULT_NETWORK_ALLOCATION_MODE
    """``managed`` (Docker assigns container IPs) or ``intent`` (honor topology static IPs)."""
    deployment_id: UUID | None = None
    project_id: UUID | None = None
    requested_by_user_id: UUID | None = None


def _node_degrees(topology: Topology) -> dict[UUID, int]:
    deg: dict[UUID, int] = {}
    for link in topology.links:
        deg[link.source_node_id] = deg.get(link.source_node_id, 0) + 1
        deg[link.target_node_id] = deg.get(link.target_node_id, 0) + 1
    return deg


def _resolve_endpoint_ip(
    *,
    link_ip: str | None,
    node_ip: str | None,
    multinet: bool,
    node_type: NodeType,
    degree: int,
    is_router_endpoint: bool,
) -> str | None:
    raw_link = (link_ip or "").strip()
    if raw_link:
        return raw_link
    raw_node = (node_ip or "").strip()
    if not raw_node:
        return None
    if multinet and node_type == NodeType.ROUTER and degree > 1 and is_router_endpoint:
        # Router on multiple segments must use per-link addresses; planner leaves unset
        # so validation can emit a clear error if still missing.
        return None
    return raw_node


def build_deployment_plan(
    topology: Topology,
    *,
    deployment_id: UUID | None = None,
    project_id: UUID | None = None,
    requested_by_user_id: UUID | None = None,
    network_allocation_mode: str | None = None,
) -> DeploymentPlan:
    """
    Produce a provider-neutral plan from ORM state.

    Expects ``topology.nodes`` and ``topology.links`` to be pre-loaded.
    """
    node_by_id = {n.id: n for n in topology.nodes}
    multinet = topology_is_segmented_multinet(topology)
    degrees = _node_degrees(topology)

    plan_links_list: list[PlanLinkDetail] = []
    legacy_links: list[tuple[str, str, str]] = []
    subnet_cidr: str | None = None

    for link in topology.links:
        if subnet_cidr is None and link.cidr:
            subnet_cidr = link.cidr
        src = node_by_id.get(link.source_node_id)
        tgt = node_by_id.get(link.target_node_id)
        if src is None or tgt is None:
            continue
        legacy_links.append((src.name, tgt.name, link.network_name))

        s_ip = _resolve_endpoint_ip(
            link_ip=link.source_endpoint_ip,
            node_ip=src.ip_address,
            multinet=multinet,
            node_type=src.node_type,
            degree=degrees.get(src.id, 0),
            is_router_endpoint=src.node_type == NodeType.ROUTER,
        )
        t_ip = _resolve_endpoint_ip(
            link_ip=link.target_endpoint_ip,
            node_ip=tgt.ip_address,
            multinet=multinet,
            node_type=tgt.node_type,
            degree=degrees.get(tgt.id, 0),
            is_router_endpoint=tgt.node_type == NodeType.ROUTER,
        )
        plan_links_list.append(
            PlanLinkDetail(
                link_id=link.id,
                source_node_id=link.source_node_id,
                target_node_id=link.target_node_id,
                source_name=src.name,
                target_name=tgt.name,
                network_name=link.network_name,
                cidr=link.cidr,
                gateway=link.gateway,
                vlan_tag=link.vlan_tag,
                source_ip=s_ip,
                target_ip=t_ip,
            )
        )

    plan_nodes = tuple(
        PlanNode(
            id=n.id,
            name=n.name,
            image=n.image,
            ip_address=n.ip_address,
            node_type=n.node_type.value,
        )
        for n in sorted(topology.nodes, key=lambda x: x.name)
    )
    node_names = tuple(n.name for n in plan_nodes)

    alloc_mode = resolve_network_allocation_mode(topology, network_allocation_mode)

    return DeploymentPlan(
        topology_id=topology.id,
        runtime_target=topology.runtime_target,
        networking_mode=topology.networking_mode,
        steps=DEFAULT_PLAN_STEPS,
        nodes=plan_nodes,
        node_names=node_names,
        links=tuple(legacy_links),
        plan_links=tuple(plan_links_list),
        segmented_networks=multinet,
        subnet_cidr=subnet_cidr,
        network_allocation_mode=alloc_mode,
        deployment_id=deployment_id,
        project_id=project_id if project_id is not None else topology.project_id,
        requested_by_user_id=requested_by_user_id,
    )
