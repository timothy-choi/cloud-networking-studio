"""Manual runtime controller — reconciliation passes and optional healing hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.topology import Topology, TopologyNode
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.providers.runtime_types import ProviderHealingResult, ProviderReconciliationResult

_last_controller_run_at: datetime | None = None


@dataclass
class ControllerRunSummary:
    deployments_checked: int
    drift_detected: int
    stopped_containers: int
    missing_containers: int
    missing_networks: int


@dataclass
class ControllerStatusSnapshot:
    controller_mode: str
    managed_deployments_count: int
    active_deployments_count: int
    supported_providers: tuple[str, ...]
    last_run_timestamp: datetime | None
    health_summary: str


@dataclass
class HealingSummaryData:
    deployment_id: UUID
    topology_id: UUID
    reconciliation: ProviderReconciliationResult
    healing: ProviderHealingResult
    skipped_missing_resources: list[str] = field(default_factory=list)


def _docker_managed_filter():
    return Deployment.runtime_target == "docker"


def _active_status_filter():
    """Deployments the controller should reconcile (live desired state at runtime)."""
    return Deployment.status == DeploymentStatus.SUCCEEDED


def _member_project_filter(user_id: UUID):
    return Project.id.in_(
        select(ProjectMembership.project_id).where(ProjectMembership.user_id == user_id)
    )


def get_controller_status(
    session: Session, *, user_id: UUID | None = None
) -> ControllerStatusSnapshot:
    if user_id is not None:
        managed_stmt = (
            select(func.count())
            .select_from(Deployment)
            .join(Topology, Deployment.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(_docker_managed_filter(), _member_project_filter(user_id))
        )
        active_stmt = (
            select(func.count())
            .select_from(Deployment)
            .join(Topology, Deployment.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(
                _docker_managed_filter(),
                _active_status_filter(),
                _member_project_filter(user_id),
            )
        )
    else:
        managed_stmt = select(func.count()).select_from(Deployment).where(_docker_managed_filter())
        active_stmt = (
            select(func.count())
            .select_from(Deployment)
            .where(_docker_managed_filter(), _active_status_filter())
        )
    managed = session.scalar(managed_stmt)
    active = session.scalar(active_stmt)
    mode = settings.controller_mode
    health = "ok"
    if active and active > 0:
        health = f"tracking {active} active Docker deployment(s)"
    else:
        health = "no active Docker deployments"
    return ControllerStatusSnapshot(
        controller_mode=mode,
        managed_deployments_count=int(managed or 0),
        active_deployments_count=int(active or 0),
        supported_providers=("docker",),
        last_run_timestamp=_last_controller_run_at,
        health_summary=health,
    )


def run_controller_once(
    session: Session, *, user_id: UUID | None = None
) -> ControllerRunSummary:
    """Reconcile every active Docker deployment; emit controller deployment events."""
    global _last_controller_run_at

    if user_id is not None:
        stmt = (
            select(Deployment)
            .join(Topology, Deployment.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(
                _docker_managed_filter(),
                _active_status_filter(),
                _member_project_filter(user_id),
            )
        )
    else:
        stmt = select(Deployment).where(_docker_managed_filter(), _active_status_filter())
    stmt = stmt.order_by(Deployment.created_at.asc())
    deps = list(session.scalars(stmt).all())

    drift_deployments = 0
    total_stopped = 0
    total_missing_nodes = 0
    total_missing_nets = 0

    for dep in deps:
        topo = session.get(Topology, dep.topology_id)
        if topo is None:
            continue
        nodes = list(
            session.scalars(
                select(TopologyNode).where(TopologyNode.topology_id == topo.id)
            ).all()
        )
        desired = frozenset(n.id for n in nodes)
        provider = runtime_provider_for_topology(dep.runtime_target)

        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message="Runtime controller run started",
            )
        )

        result = provider.reconcile_runtime(topo.id, desired)

        has_drift = (
            result.missing_network
            or bool(result.missing_node_ids)
            or bool(result.stopped_containers)
        )
        if has_drift:
            drift_deployments += 1
            session.add(
                DeploymentEvent(
                    deployment_id=dep.id,
                    level=DeploymentEventLevel.WARNING,
                    message=(
                        "Drift detected by controller: "
                        f"missing_network={result.missing_network}, "
                        f"missing_nodes={len(result.missing_node_ids)}, "
                        f"stopped_containers={len(result.stopped_containers)}"
                    ),
                )
            )

        if result.missing_network:
            total_missing_nets += 1
        total_missing_nodes += len(result.missing_node_ids)
        total_stopped += len(result.stopped_containers)

        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message="Runtime controller run completed",
            )
        )

    _last_controller_run_at = datetime.now(UTC)

    return ControllerRunSummary(
        deployments_checked=len(deps),
        drift_detected=drift_deployments,
        stopped_containers=total_stopped,
        missing_containers=total_missing_nodes,
        missing_networks=total_missing_nets,
    )


def heal_deployment(session: Session, deployment_id: UUID) -> HealingSummaryData:
    """Reconcile, emit skip messages for absent resources, restart stopped containers."""
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

    session.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message="Healing started",
        )
    )

    result = provider.reconcile_runtime(topo.id, desired)

    skipped: list[str] = []
    if result.missing_network:
        skipped.append("topology_network")
        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=(
                    "Healing skipped for missing resource: managed Docker network "
                    "(full topology recreate not performed)"
                ),
            )
        )
    for nid in result.missing_node_ids:
        skipped.append(f"node:{nid}")
        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=(
                    f"Healing skipped for missing resource: container for node_id={nid} "
                    "(recreate not performed in this step)"
                ),
            )
        )

    for cid, name in result.stopped_containers:
        sid = cid[:12] if cid else "?"
        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message=f"Restarting stopped container: {name} ({sid})",
            )
        )

    heal_out = provider.heal_restart_stopped(topo.id)

    for cid, name in heal_out.restarted:
        sid = cid[:12] if cid else "?"
        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message=f"Container restarted: {name} ({sid})",
            )
        )

    for err in heal_out.errors:
        session.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=f"Healing error while restarting: {err}",
            )
        )

    session.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message="Healing completed",
        )
    )

    return HealingSummaryData(
        deployment_id=dep.id,
        topology_id=topo.id,
        reconciliation=result,
        healing=heal_out,
        skipped_missing_resources=skipped,
    )
