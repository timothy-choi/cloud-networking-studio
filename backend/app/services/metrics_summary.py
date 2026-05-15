"""Aggregate metrics for GET /metrics/summary (read-only; no deployment behavior changes)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentEvent, DeploymentStatus
from app.models.failure_injection import FailureInjection, FailureInjectionStatus
from app.models.topology import Topology
from app.models.traffic_test import TrafficTest, TrafficTestStatus
from app.schemas.metrics import MetricsLatestEvent, MetricsSummaryResponse


def _docker_managed_expr():
    return Deployment.runtime_target == "docker"


def build_metrics_summary(session: Session, *, latest_event_limit: int = 40) -> MetricsSummaryResponse:
    total_topologies = int(
        session.scalar(select(func.count()).select_from(Topology)) or 0
    )
    total_deployments = int(
        session.scalar(select(func.count()).select_from(Deployment)) or 0
    )
    active_deployments = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(_docker_managed_expr(), Deployment.status == DeploymentStatus.SUCCEEDED)
        )
        or 0
    )
    failed_deployments = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(Deployment.status == DeploymentStatus.FAILED)
        )
        or 0
    )

    total_traffic_tests = int(
        session.scalar(select(func.count()).select_from(TrafficTest)) or 0
    )
    failed_traffic_tests = int(
        session.scalar(
            select(func.count())
            .select_from(TrafficTest)
            .where(TrafficTest.status == TrafficTestStatus.FAILED)
        )
        or 0
    )

    total_failure_injections = int(
        session.scalar(select(func.count()).select_from(FailureInjection)) or 0
    )
    failed_failure_injections = int(
        session.scalar(
            select(func.count())
            .select_from(FailureInjection)
            .where(FailureInjection.status == FailureInjectionStatus.FAILED)
        )
        or 0
    )

    ev_stmt = (
        select(DeploymentEvent, Deployment.topology_id)
        .join(Deployment, DeploymentEvent.deployment_id == Deployment.id)
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
