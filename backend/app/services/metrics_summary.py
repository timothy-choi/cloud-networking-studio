"""Aggregate metrics for GET /metrics/summary (read-only; scoped to one user's projects)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentEvent, DeploymentStatus
from app.models.failure_injection import FailureInjection, FailureInjectionStatus
from app.models.project import Project
from app.models.topology import Topology
from app.models.traffic_test import TrafficTest, TrafficTestStatus
from app.schemas.metrics import MetricsLatestEvent, MetricsSummaryResponse


def _docker_managed_expr():
    return Deployment.runtime_target == "docker"


def _owned_deployment_ids_subquery(owner_user_id: uuid.UUID):
    return (
        select(Deployment.id)
        .join(Topology, Deployment.topology_id == Topology.id)
        .join(Project, Topology.project_id == Project.id)
        .where(Project.owner_user_id == owner_user_id)
    )


def build_metrics_summary(
    session: Session,
    *,
    owner_user_id: uuid.UUID,
    latest_event_limit: int = 40,
) -> MetricsSummaryResponse:
    owned_deployments = _owned_deployment_ids_subquery(owner_user_id)

    total_topologies = int(
        session.scalar(
            select(func.count())
            .select_from(Topology)
            .join(Project, Topology.project_id == Project.id)
            .where(Project.owner_user_id == owner_user_id)
        )
        or 0
    )
    total_deployments = int(
        session.scalar(
            select(func.count()).select_from(Deployment).where(Deployment.id.in_(owned_deployments))
        )
        or 0
    )
    active_deployments = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(
                Deployment.id.in_(owned_deployments),
                _docker_managed_expr(),
                Deployment.status == DeploymentStatus.SUCCEEDED,
            )
        )
        or 0
    )
    failed_deployments = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(
                Deployment.id.in_(owned_deployments),
                Deployment.status == DeploymentStatus.FAILED,
            )
        )
        or 0
    )

    total_traffic_tests = int(
        session.scalar(
            select(func.count())
            .select_from(TrafficTest)
            .join(Topology, TrafficTest.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(Project.owner_user_id == owner_user_id)
        )
        or 0
    )
    failed_traffic_tests = int(
        session.scalar(
            select(func.count())
            .select_from(TrafficTest)
            .join(Topology, TrafficTest.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(
                Project.owner_user_id == owner_user_id,
                TrafficTest.status == TrafficTestStatus.FAILED,
            )
        )
        or 0
    )

    total_failure_injections = int(
        session.scalar(
            select(func.count())
            .select_from(FailureInjection)
            .join(Topology, FailureInjection.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(Project.owner_user_id == owner_user_id)
        )
        or 0
    )
    failed_failure_injections = int(
        session.scalar(
            select(func.count())
            .select_from(FailureInjection)
            .join(Topology, FailureInjection.topology_id == Topology.id)
            .join(Project, Topology.project_id == Project.id)
            .where(
                Project.owner_user_id == owner_user_id,
                FailureInjection.status == FailureInjectionStatus.FAILED,
            )
        )
        or 0
    )

    ev_stmt = (
        select(DeploymentEvent, Deployment.topology_id)
        .join(Deployment, DeploymentEvent.deployment_id == Deployment.id)
        .where(Deployment.id.in_(owned_deployments))
        .order_by(DeploymentEvent.created_at.desc())
        .limit(latest_event_limit)
    )
    rows = session.execute(ev_stmt).all()
    latest_events: list[MetricsLatestEvent] = []
    for ev, topology_id in rows:
        latest_events.append(
            MetricsLatestEvent(
                id=ev.id,
                source="deployment_event",
                topology_id=topology_id,
                deployment_id=ev.deployment_id,
                level=ev.level,
                message=ev.message,
                created_at=ev.created_at,
            )
        )

    return MetricsSummaryResponse(
        total_topologies=total_topologies,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        failed_deployments=failed_deployments,
        total_traffic_tests=total_traffic_tests,
        failed_traffic_tests=failed_traffic_tests,
        total_failure_injections=total_failure_injections,
        failed_failure_injections=failed_failure_injections,
        latest_events=latest_events,
    )
