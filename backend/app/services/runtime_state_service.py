"""Aggregate runtime views — keeps Docker/client specifics inside providers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel
from app.models.topology import Topology, TopologyNode
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.services.deployment_queries import latest_deployment_for_topology
from app.providers.runtime_types import (
    ProviderReconciliationResult,
    ProviderRuntimeSnapshot,
    ProviderRuntimeStats,
)
from app.schemas.runtime import (
    RuntimeContainerResponse,
    RuntimeDeploymentResponse,
    RuntimeLogsResponse,
    RuntimeNetworkInterfaceResponse,
    RuntimeNetworkResponse,
    RuntimeStatsResponse,
    RuntimeTopologyResponse,
)


def _snapshot_to_networks(snap: ProviderRuntimeSnapshot) -> list[RuntimeNetworkResponse]:
    out: list[RuntimeNetworkResponse] = []
    for n in snap.networks:
        out.append(
            RuntimeNetworkResponse(
                network_id=n.network_id,
                name=n.name,
                driver=n.driver,
                labels=dict(n.labels),
                scope=n.scope,
                ipam_driver=n.ipam_driver,
                subnet_hints=list(n.subnet_hints),
            )
        )
    return out


def _snapshot_to_containers(snap: ProviderRuntimeSnapshot) -> list[RuntimeContainerResponse]:
    out: list[RuntimeContainerResponse] = []
    for c in snap.containers:
        out.append(
            RuntimeContainerResponse(
                container_id=c.container_id,
                short_id=c.short_id,
                name=c.name,
                image=c.image,
                status=c.status,
                state_status=c.state_status,
                running=c.running,
                labels=dict(c.labels),
                node_id=c.node_id,
                ipv4_by_network=dict(c.ipv4_by_network),
                network_interfaces=[
                    RuntimeNetworkInterfaceResponse(
                        docker_network=i.docker_network,
                        interface=i.interface,
                        ipv4=i.ipv4,
                        gateway=i.gateway,
                        logical_network=i.logical_network,
                    )
                    for i in c.network_interfaces
                ],
                routes_lines=list(c.routes_lines),
                interface_lines=list(c.interface_lines),
                ip_forward_enabled=c.ip_forward_enabled,
                forwarding_role=c.forwarding_role,
                created=c.created,
                started_at=c.started_at,
            )
        )
    return out


def _node_mappings(
    nodes: list[TopologyNode],
    snap: ProviderRuntimeSnapshot,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build node_id -> container_id and container_id -> status maps."""
    by_node: dict[str, str] = {}
    states: dict[str, str] = {}
    for c in snap.containers:
        states[c.container_id] = c.status
        if c.node_id is not None:
            by_node[str(c.node_id)] = c.container_id
    # desired nodes without runtime still absent from by_node
    _ = nodes  # reserved if we need explicit "expected" keys later
    return by_node, states


def record_runtime_inspection_event(
    session: Session,
    topology_id: UUID,
    snap: ProviderRuntimeSnapshot,
    source: str,
) -> None:
    dep = latest_deployment_for_topology(session, topology_id)
    if dep is None:
        return
    msg = (
        f"Runtime inspection ({source}): {len(snap.networks)} network(s), "
        f"{len(snap.containers)} container(s)."
    )
    session.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message=msg,
        )
    )


def record_logs_requested_event(
    session: Session, topology_id: UUID, node_id: UUID, tail: int
) -> None:
    dep = latest_deployment_for_topology(session, topology_id)
    if dep is None:
        return
    session.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message=f"Runtime logs requested for node_id={node_id} (tail={tail}).",
        )
    )


def record_stats_requested_event(
    session: Session, topology_id: UUID, node_id: UUID
) -> None:
    dep = latest_deployment_for_topology(session, topology_id)
    if dep is None:
        return
    session.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message=f"Runtime stats requested for node_id={node_id}.",
        )
    )


def build_topology_runtime(
    session: Session,
    topology_id: UUID,
    *,
    emit_inspection_event: bool = False,
) -> RuntimeTopologyResponse:
    topo = session.get(Topology, topology_id)
    if topo is None:
        raise ValueError("topology not found")
    provider = runtime_provider_for_topology(topo.runtime_target)
    snap = provider.inspect_topology_runtime(topology_id)
    nodes = list(
        session.scalars(
            select(TopologyNode).where(TopologyNode.topology_id == topology_id)
        ).all()
    )
    latest = latest_deployment_for_topology(session, topology_id)
    mapping, states = _node_mappings(nodes, snap)
    if emit_inspection_event:
        record_runtime_inspection_event(
            session, topology_id, snap, "GET /topologies/{id}/runtime"
        )
    return RuntimeTopologyResponse(
        topology_id=topology_id,
        deployment_status=latest.status if latest else None,
        latest_deployment_id=latest.id if latest else None,
        runtime_provider=topo.runtime_target,
        networks=_snapshot_to_networks(snap),
        containers=_snapshot_to_containers(snap),
        node_runtime_mapping=mapping,
        container_states=states,
    )


def build_deployment_runtime(
    session: Session,
    deployment_id: UUID,
    *,
    emit_inspection_event: bool = False,
) -> RuntimeDeploymentResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    provider = runtime_provider_for_topology(dep.runtime_target)
    snap = provider.inspect_topology_runtime(dep.topology_id)
    nodes = list(
        session.scalars(
            select(TopologyNode).where(TopologyNode.topology_id == dep.topology_id)
        ).all()
    )
    mapping, states = _node_mappings(nodes, snap)
    if emit_inspection_event:
        record_runtime_inspection_event(
            session, dep.topology_id, snap, "GET /deployments/{id}/runtime"
        )
    return RuntimeDeploymentResponse(
        deployment_id=dep.id,
        topology_id=dep.topology_id,
        runtime_provider=dep.runtime_target,
        deployment_status=dep.status,
        networks=_snapshot_to_networks(snap),
        containers=_snapshot_to_containers(snap),
        node_runtime_mapping=mapping,
        container_states=states,
    )


def build_node_logs(
    session: Session, node_id: UUID, tail: int
) -> RuntimeLogsResponse | None:
    node = session.get(TopologyNode, node_id)
    if node is None:
        raise ValueError("node not found")
    topo = session.get(Topology, node.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    provider = runtime_provider_for_topology(topo.runtime_target)
    latest = latest_deployment_for_topology(session, node.topology_id)
    dep_id = latest.id if latest else None
    text = provider.fetch_logs_for_node(
        node.topology_id,
        node_id,
        tail,
        deployment_id=dep_id,
        project_id=topo.project_id,
    )
    if text is None:
        return None
    return RuntimeLogsResponse(
        node_id=node_id,
        topology_id=node.topology_id,
        tail=tail,
        logs=text,
    )


def build_node_stats(
    session: Session, node_id: UUID
) -> RuntimeStatsResponse | None:
    node = session.get(TopologyNode, node_id)
    if node is None:
        raise ValueError("node not found")
    topo = session.get(Topology, node.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    provider = runtime_provider_for_topology(topo.runtime_target)
    raw = provider.fetch_stats_for_node(node.topology_id, node_id)
    if raw is None:
        return None
    return _stats_to_response(node_id, node.topology_id, raw)


def _stats_to_response(
    node_id: UUID, topology_id: UUID, raw: ProviderRuntimeStats
) -> RuntimeStatsResponse:
    return RuntimeStatsResponse(
        node_id=node_id,
        topology_id=topology_id,
        cpu_percent=raw.cpu_percent,
        memory_usage_bytes=raw.memory_usage_bytes,
        memory_limit_bytes=raw.memory_limit_bytes,
        network_rx_bytes=raw.network_rx_bytes,
        network_tx_bytes=raw.network_tx_bytes,
    )


def reconcile_deployment(
    session: Session, deployment_id: UUID
) -> tuple[Deployment, ProviderReconciliationResult]:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    nodes = list(
        session.scalars(
            select(TopologyNode).where(TopologyNode.topology_id == topo.id)
        ).all()
    )
    desired = frozenset(n.id for n in nodes)
    provider = runtime_provider_for_topology(dep.runtime_target)
    result = provider.reconcile_runtime(topo.id, desired)
    return dep, result
