"""Aggregate runtime views — keeps Docker/client specifics inside providers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import (
    Deployment,
    DeploymentCleanupStatus,
    DeploymentEvent,
    DeploymentEventLevel,
    DeploymentStatus,
    TopologySyncStatus,
)
from app.models.topology import Topology, TopologyNode
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.services.deployment_queries import latest_deployment_for_topology
from app.services.deployment_runtime_resource_service import (
    list_runtime_resources,
    resource_row_to_public_dict,
)
from app.services.deployment_service_exposure_service import (
    exposure_to_api_dict,
    list_exposure_rows,
)
from app.services.runtime_access_instructions import (
    build_runtime_instructions,
    deployment_access_status_label,
)
from app.providers.runtime_types import (
    ProviderReconciliationResult,
    ProviderRuntimeSnapshot,
    ProviderRuntimeStats,
)
from app.schemas.runtime import (
    RuntimeContainerResponse,
    RuntimeDeploymentResponse,
    RuntimeDeploymentSectionResponse,
    RuntimeDeploymentServicesSectionResponse,
    RuntimeInstructionsOnlyResponse,
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


def _primary_runtime_ipv4(c) -> str | None:
    if c.actual_runtime_ip:
        return c.actual_runtime_ip
    if c.network_interfaces:
        for iface in c.network_interfaces:
            if iface.ipv4:
                return iface.ipv4
    if c.ipv4_by_network:
        return next(iter(c.ipv4_by_network.values()), None)
    return None


def _snapshot_to_containers(
    snap: ProviderRuntimeSnapshot,
    intent_by_node: dict[UUID, str | None] | None = None,
) -> list[RuntimeContainerResponse]:
    out: list[RuntimeContainerResponse] = []
    intent_by_node = intent_by_node or {}
    for c in snap.containers:
        intended = c.intended_ip
        if intended is None and c.node_id is not None:
            intended = intent_by_node.get(c.node_id)
        actual = _primary_runtime_ipv4(c)
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
                intended_ip=intended,
                actual_runtime_ip=actual,
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


def _enum_str(val: object | None) -> str | None:
    if val is None:
        return None
    if hasattr(val, "value"):
        return str(getattr(val, "value"))
    return str(val)


def _empty_topology_runtime_response(
    *,
    topology_id: UUID,
    runtime_provider: str,
    status: str,
    latest: Deployment | None = None,
    resources: list[dict] | None = None,
    warning: str | None = None,
    message: str | None = None,
) -> RuntimeTopologyResponse:
    return RuntimeTopologyResponse(
        topology_id=topology_id,
        status=status,
        resources=list(resources or []),
        warning=warning,
        message=message,
        deployment_status=latest.status if latest else None,
        latest_deployment_id=latest.id if latest else None,
        topology_sync_status=_enum_str(latest.topology_sync_status) if latest else None,
        runtime_provider=runtime_provider or "docker",
        networks=[],
        containers=[],
        node_runtime_mapping={},
        container_states={},
    )


def _resolve_topology_runtime_status(
    latest: Deployment,
    snap: ProviderRuntimeSnapshot,
    resources: list[dict],
    *,
    provider_warning: str | None = None,
) -> tuple[str, str | None]:
    sync_status = _enum_str(latest.topology_sync_status)
    warning = provider_warning

    if latest.status == DeploymentStatus.STOPPED:
        return "destroyed", warning

    if (
        latest.status == DeploymentStatus.SUCCEEDED
        and latest.cleanup_status == DeploymentCleanupStatus.CLEAN
        and not snap.containers
        and not snap.networks
        and not resources
    ):
        cleaned = "Deployment resources have been cleaned up."
        warning = f"{warning} {cleaned}".strip() if warning else cleaned
        return "destroyed", warning

    if latest.status == DeploymentStatus.FAILED:
        return "failed", warning

    if latest.status in (
        DeploymentStatus.PENDING,
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.STOPPING,
    ):
        return "pending", warning

    if sync_status == TopologySyncStatus.OUT_OF_SYNC.value:
        drift = (
            "Topology definition changed since the last deploy; "
            "runtime may not match current intent."
        )
        warning = f"{warning} {drift}".strip() if warning else drift
        if not snap.containers and not snap.networks and not resources:
            return "out_of_sync", warning
        return "out_of_sync", warning

    if latest.status == DeploymentStatus.SUCCEEDED:
        if not snap.containers and not snap.networks and not resources:
            missing = "No live or persisted runtime resources found for the active deployment."
            warning = f"{warning} {missing}".strip() if warning else missing
            return "no_runtime_resources", warning
        if provider_warning:
            return "degraded", warning
        return "running", warning

    return "degraded", warning


def _inspect_topology_runtime_safe(
    runtime_target: str | None,
    topology_id: UUID,
) -> tuple[ProviderRuntimeSnapshot, str | None]:
    try:
        provider = runtime_provider_for_topology(runtime_target or "docker")
    except Exception as exc:  # noqa: BLE001 — provider selection must not 500 the API
        return ProviderRuntimeSnapshot(), f"Runtime provider unavailable: {exc}"
    try:
        snap = provider.inspect_topology_runtime(topology_id)
    except Exception as exc:  # noqa: BLE001 — live inspection is best-effort
        return ProviderRuntimeSnapshot(), f"Runtime inspection failed: {exc}"
    client_error = getattr(getattr(provider, "_docker", provider), "_client_error", None)
    if client_error and not snap.containers and not snap.networks:
        return snap, f"Docker engine unavailable: {client_error}"
    return snap, None


def build_topology_runtime(
    session: Session,
    topology_id: UUID,
    *,
    emit_inspection_event: bool = False,
) -> RuntimeTopologyResponse:
    topo = session.get(Topology, topology_id)
    if topo is None:
        raise ValueError("topology not found")

    runtime_provider = topo.runtime_target or "docker"
    latest = latest_deployment_for_topology(session, topology_id)
    if latest is None:
        return _empty_topology_runtime_response(
            topology_id=topology_id,
            runtime_provider=runtime_provider,
            status="not_deployed",
        )

    if latest.status == DeploymentStatus.STOPPED:
        msg = "Deployment resources have been cleaned up."
        if latest.cleanup_status == DeploymentCleanupStatus.CLEAN:
            return _empty_topology_runtime_response(
                topology_id=topology_id,
                runtime_provider=runtime_provider,
                status="destroyed",
                latest=latest,
                message=msg,
            )
        return _empty_topology_runtime_response(
            topology_id=topology_id,
            runtime_provider=runtime_provider,
            status="destroyed",
            latest=latest,
            message="Deployment has been destroyed.",
        )

    resources = [
        resource_row_to_public_dict(r)
        for r in list_runtime_resources(session, latest.id)
    ]
    snap, provider_warning = _inspect_topology_runtime_safe(runtime_provider, topology_id)
    nodes = list(
        session.scalars(
            select(TopologyNode).where(TopologyNode.topology_id == topology_id)
        ).all()
    )
    mapping, states = _node_mappings(nodes, snap)
    coarse_status, warning = _resolve_topology_runtime_status(
        latest,
        snap,
        resources,
        provider_warning=provider_warning,
    )
    message: str | None = None
    if coarse_status == "destroyed":
        message = "Deployment resources have been cleaned up."
    if emit_inspection_event:
        record_runtime_inspection_event(
            session, topology_id, snap, "GET /topologies/{id}/runtime"
        )
    return RuntimeTopologyResponse(
        topology_id=topology_id,
        status=coarse_status,
        resources=resources if coarse_status != "destroyed" else [],
        warning=warning,
        message=message,
        deployment_status=latest.status,
        latest_deployment_id=latest.id,
        topology_sync_status=_enum_str(latest.topology_sync_status),
        runtime_provider=runtime_provider,
        networks=_snapshot_to_networks(snap) if coarse_status != "destroyed" else [],
        containers=_snapshot_to_containers(
            snap,
            {n.id: (n.ip_address or None) for n in nodes},
        )
        if coarse_status != "destroyed"
        else [],
        node_runtime_mapping=mapping if coarse_status != "destroyed" else {},
        container_states=states if coarse_status != "destroyed" else {},
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
    persisted = list_runtime_resources(session, deployment_id)
    pub_rows = [resource_row_to_public_dict(r) for r in persisted]
    nodes_pub = [r for r in pub_rows if r.get("type") == "node"]
    services_pub = [r for r in pub_rows if r.get("type") == "service"]
    endpoints_pub: list[dict] = []
    for r in pub_rows:
        if r.get("internal_url"):
            endpoints_pub.append(
                {
                    "kind": r.get("type"),
                    "name": r.get("name"),
                    "internal_url": r.get("internal_url"),
                    "external_url": r.get("external_url"),
                }
            )
    ns_net = next((r.get("namespace_or_network") for r in pub_rows if r.get("namespace_or_network")), None)
    exposure_rows = list_exposure_rows(session, deployment_id)
    exposures_pub = [exposure_to_api_dict(e) for e in exposure_rows]
    instructions = build_runtime_instructions(
        deployment=dep,
        topology=topo,
        resources=pub_rows,
        exposures=exposures_pub,
    )
    if emit_inspection_event:
        record_runtime_inspection_event(
            session, dep.topology_id, snap, "GET /deployments/{id}/runtime"
        )
    return RuntimeDeploymentResponse(
        deployment_id=dep.id,
        topology_id=dep.topology_id,
        runtime_provider=dep.runtime_target,
        deployment_status=dep.status,
        topology_sync_status=(
            dep.topology_sync_status.value
            if hasattr(dep.topology_sync_status, "value")
            else str(dep.topology_sync_status)
        ),
        networks=_snapshot_to_networks(snap),
        containers=_snapshot_to_containers(
            snap,
            {n.id: (n.ip_address or None) for n in nodes},
        ),
        node_runtime_mapping=mapping,
        container_states=states,
        status=deployment_access_status_label(dep),
        namespace_or_network=ns_net,
        nodes=nodes_pub,
        services=services_pub,
        endpoints=endpoints_pub,
        instructions=instructions,
        exposures=exposures_pub,
    )


def build_deployment_runtime_nodes_section(
    session: Session, deployment_id: UUID
) -> RuntimeDeploymentSectionResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    pub = [resource_row_to_public_dict(r) for r in list_runtime_resources(session, deployment_id)]
    return RuntimeDeploymentSectionResponse(
        deployment_id=dep.id,
        nodes=[r for r in pub if r.get("type") == "node"],
    )


def build_deployment_runtime_services_section(
    session: Session, deployment_id: UUID
) -> RuntimeDeploymentServicesSectionResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    pub = [resource_row_to_public_dict(r) for r in list_runtime_resources(session, deployment_id)]
    return RuntimeDeploymentServicesSectionResponse(
        deployment_id=dep.id,
        services=[r for r in pub if r.get("type") == "service"],
    )


def build_deployment_runtime_instructions_section(
    session: Session, deployment_id: UUID
) -> RuntimeInstructionsOnlyResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    pub = [resource_row_to_public_dict(r) for r in list_runtime_resources(session, deployment_id)]
    exposure_rows = list_exposure_rows(session, deployment_id)
    exposures_pub = [exposure_to_api_dict(e) for e in exposure_rows]
    return RuntimeInstructionsOnlyResponse(
        deployment_id=dep.id,
        instructions=build_runtime_instructions(
            deployment=dep, topology=topo, resources=pub, exposures=exposures_pub
        ),
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
