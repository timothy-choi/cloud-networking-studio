"""Platform / project / deployment metrics aggregation (Step 53C)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.deployment import Deployment, DeploymentStatus
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.topology import Topology
from app.runtime.go_runner_client import effective_runtime_executor
from app.schemas.platform_metrics import (
    ApiRequestMetrics,
    CleanupStatusMetrics,
    DeploymentDurationMetrics,
    DeploymentMetricsResponse,
    FailedOperationMetrics,
    PlatformMetricsResponse,
    ProjectMetricsResponse,
    QuotaUsageMetrics,
    RuntimeProviderStatusMetrics,
)
from app.services.cleanup_service import build_cleanup_status, is_deployment_expired
from app.services.quota_service import build_project_quota_usage, quota_limits
from app.services.request_metrics import api_request_metrics


def _member_project_ids_subquery(user_id: uuid.UUID):
    return select(ProjectMembership.project_id).where(ProjectMembership.user_id == user_id)


def _scoped_deployment_ids_subquery(user_id: uuid.UUID):
    return (
        select(Deployment.id)
        .join(Topology, Deployment.topology_id == Topology.id)
        .where(Topology.project_id.in_(_member_project_ids_subquery(user_id)))
    )


def _project_deployment_ids_subquery(project_id: UUID):
    return (
        select(Deployment.id)
        .join(Topology, Deployment.topology_id == Topology.id)
        .where(Topology.project_id == project_id)
    )


def _runtime_provider_status() -> RuntimeProviderStatusMetrics:
    executor = effective_runtime_executor()
    if executor == "go":
        from app.runtime.go_runner_client import GoRunnerClient

        try:
            data = GoRunnerClient.from_settings().get_runtime_status()
            if isinstance(data, dict):
                return RuntimeProviderStatusMetrics(
                    status=str(data.get("status") or "ok"),
                    runtime_executor=executor,
                    runtime_provider=str(data.get("runtime_provider") or "") or None,
                    runner_reachable=True,
                    docker_reachable=bool(data.get("docker_reachable")),
                    kubernetes_reachable=bool(data.get("kubernetes_reachable")),
                    message=str(data.get("message") or "") or None,
                )
        except Exception as exc:  # noqa: BLE001
            return RuntimeProviderStatusMetrics(
                status="degraded",
                runtime_executor=executor,
                runner_reachable=False,
                message=str(exc),
            )
    fake = os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes")
    if fake:
        return RuntimeProviderStatusMetrics(
            status="ok",
            runtime_executor=executor,
            runtime_provider="docker",
            docker_reachable=True,
            message="CNS_USE_FAKE_DOCKER",
        )
    docker_ok = False
    msg: str | None = None
    try:
        import docker as docker_mod

        docker_mod.from_env().ping()
        docker_ok = True
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
    return RuntimeProviderStatusMetrics(
        status="ok" if docker_ok else "degraded",
        runtime_executor=executor,
        runtime_provider="docker",
        docker_reachable=docker_ok,
        message=msg,
    )


def _deploy_duration_metrics(session: Session, deployment_ids_subq) -> DeploymentDurationMetrics:
    rows = session.execute(
        select(Deployment.started_at, Deployment.finished_at).where(
            Deployment.id.in_(deployment_ids_subq),
            Deployment.started_at.is_not(None),
            Deployment.finished_at.is_not(None),
            Deployment.status.in_((DeploymentStatus.SUCCEEDED, DeploymentStatus.FAILED)),
        )
    ).all()
    durations: list[float] = []
    for started, finished in rows:
        if started and finished:
            s = started if started.tzinfo else started.replace(tzinfo=UTC)
            f = finished if finished.tzinfo else finished.replace(tzinfo=UTC)
            durations.append(max(0.0, (f - s).total_seconds()))
    if not durations:
        return DeploymentDurationMetrics(average_deploy_duration_seconds=None, sample_count=0)
    return DeploymentDurationMetrics(
        average_deploy_duration_seconds=sum(durations) / len(durations),
        sample_count=len(durations),
    )


def _count_by_status(session: Session, deployment_ids_subq) -> tuple[int, int, int]:
    active = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(
                Deployment.id.in_(deployment_ids_subq),
                Deployment.status.in_(
                    (
                        DeploymentStatus.PENDING,
                        DeploymentStatus.DEPLOYING,
                        DeploymentStatus.STOPPING,
                        DeploymentStatus.SUCCEEDED,
                    )
                ),
            )
        )
        or 0
    )
    succeeded = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(
                Deployment.id.in_(deployment_ids_subq),
                Deployment.status == DeploymentStatus.SUCCEEDED,
            )
        )
        or 0
    )
    failed = int(
        session.scalar(
            select(func.count())
            .select_from(Deployment)
            .where(
                Deployment.id.in_(deployment_ids_subq),
                Deployment.status == DeploymentStatus.FAILED,
            )
        )
        or 0
    )
    return active, succeeded, failed


def _active_terminal_sessions(session: Session, *, user_id: UUID | None = None, project_id: UUID | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(DeploymentRuntimeTerminalSession)
        .join(Deployment, DeploymentRuntimeTerminalSession.deployment_id == Deployment.id)
        .join(Topology, Deployment.topology_id == Topology.id)
        .where(DeploymentRuntimeTerminalSession.status.in_(("opening", "active")))
    )
    if project_id is not None:
        stmt = stmt.where(Topology.project_id == project_id)
    elif user_id is not None:
        stmt = stmt.where(Topology.project_id.in_(_member_project_ids_subquery(user_id)))
    return int(session.scalar(stmt) or 0)


def _recent_failed_operations(
    session: Session,
    *,
    project_id: UUID | None = None,
    deployment_id: UUID | None = None,
    user_id: UUID | None = None,
    limit: int = 15,
) -> list[FailedOperationMetrics]:
    stmt = select(AuditLog).where(AuditLog.status.in_(("failure", "failed")))
    if deployment_id is not None:
        stmt = stmt.where(
            AuditLog.resource_type == "deployment",
            AuditLog.resource_id == str(deployment_id),
        )
    elif project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    elif user_id is not None:
        stmt = stmt.where(AuditLog.project_id.in_(_member_project_ids_subquery(user_id)))
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = session.execute(stmt).scalars().all()
    out: list[FailedOperationMetrics] = []
    for row in rows:
        meta = row.metadata_json or {}
        msg = meta.get("message") or meta.get("error") or row.action
        out.append(
            FailedOperationMetrics(
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                status=row.status,
                message=str(msg) if msg is not None else None,
                request_id=row.request_id,
                created_at=row.created_at,
            )
        )
    return out


def _cleanup_status_for_scope(
    session: Session,
    deployment_ids_subq,
) -> CleanupStatusMetrics:
    deps = list(session.scalars(select(Deployment).where(Deployment.id.in_(deployment_ids_subq))).all())
    eligible = 0
    with_resources = 0
    stale_terminals = 0
    for dep in deps:
        resource_count = int(
            session.scalar(
                select(func.count())
                .select_from(DeploymentRuntimeResource)
                .where(DeploymentRuntimeResource.deployment_id == dep.id)
            )
            or 0
        )
        if resource_count > 0:
            with_resources += 1
        stale_terminals += int(
            session.scalar(
                select(func.count())
                .select_from(DeploymentRuntimeTerminalSession)
                .where(
                    DeploymentRuntimeTerminalSession.deployment_id == dep.id,
                    DeploymentRuntimeTerminalSession.status.in_(("opening", "active")),
                )
            )
            or 0
        )
        if (
            dep.status in (DeploymentStatus.FAILED, DeploymentStatus.STOPPED)
            or is_deployment_expired(dep)
            or resource_count > 0
        ):
            eligible += 1
    return CleanupStatusMetrics(
        eligible_deployments=eligible,
        deployments_with_runtime_resources=with_resources,
        stale_terminal_sessions=stale_terminals,
    )


def _api_metrics() -> ApiRequestMetrics:
    raw = api_request_metrics()
    by_status = raw.get("by_status") or {}
    return ApiRequestMetrics(
        total_requests=int(raw.get("total_requests") or 0),
        by_status={str(k): int(v) for k, v in by_status.items()},
    )


def _aggregate_quota_usage(session: Session, user_id: UUID) -> QuotaUsageMetrics:
    projects = list(
        session.scalars(
            select(Project.id).where(Project.id.in_(_member_project_ids_subquery(user_id)))
        ).all()
    )
    if not projects:
        return QuotaUsageMetrics(
            active_deployments=0,
            terminal_sessions=0,
            api_tokens=0,
            limits=quota_limits(),
        )
    active = 0
    terminals = 0
    tokens = 0
    limits: dict[str, int] | None = None
    for pid in projects:
        raw = build_project_quota_usage(session, pid, user_id)
        active += int(raw["usage"]["active_deployments"])
        terminals = max(terminals, int(raw["usage"]["terminal_sessions"]))
        tokens = max(tokens, int(raw["usage"]["api_tokens"]))
        limits = raw["limits"]
    return QuotaUsageMetrics(
        active_deployments=active,
        terminal_sessions=terminals,
        api_tokens=tokens,
        limits=limits or {},
    )


def build_platform_metrics(session: Session, *, user_id: UUID) -> PlatformMetricsResponse:
    dep_subq = _scoped_deployment_ids_subquery(user_id)
    active, succeeded, failed = _count_by_status(session, dep_subq)
    return PlatformMetricsResponse(
        active_deployments=active,
        deployment_success_count=succeeded,
        deployment_failure_count=failed,
        deploy_duration=_deploy_duration_metrics(session, dep_subq),
        active_terminal_sessions=_active_terminal_sessions(session, user_id=user_id),
        runtime_provider_status=_runtime_provider_status(),
        quota_usage=_aggregate_quota_usage(session, user_id),
        recent_failed_operations=_recent_failed_operations(session, user_id=user_id),
        cleanup_status=_cleanup_status_for_scope(session, dep_subq),
        api_requests=_api_metrics(),
    )


def build_project_metrics(session: Session, *, project_id: UUID, user_id: UUID) -> ProjectMetricsResponse:
    dep_subq = _project_deployment_ids_subquery(project_id)
    active, succeeded, failed = _count_by_status(session, dep_subq)
    quota_raw = build_project_quota_usage(session, project_id, user_id)
    return ProjectMetricsResponse(
        project_id=project_id,
        active_deployments=active,
        deployment_success_count=succeeded,
        deployment_failure_count=failed,
        deploy_duration=_deploy_duration_metrics(session, dep_subq),
        active_terminal_sessions=_active_terminal_sessions(session, project_id=project_id),
        quota_usage=QuotaUsageMetrics(
            active_deployments=int(quota_raw["usage"]["active_deployments"]),
            terminal_sessions=int(quota_raw["usage"]["terminal_sessions"]),
            api_tokens=int(quota_raw["usage"]["api_tokens"]),
            limits=quota_raw["limits"],
        ),
        recent_failed_operations=_recent_failed_operations(session, project_id=project_id),
        cleanup_status=_cleanup_status_for_scope(session, dep_subq),
    )


def build_deployment_metrics(session: Session, *, deployment_id: UUID) -> DeploymentMetricsResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    cleanup = build_cleanup_status(session, deployment_id)
    duration: float | None = None
    if dep.started_at and dep.finished_at:
        s = dep.started_at if dep.started_at.tzinfo else dep.started_at.replace(tzinfo=UTC)
        f = dep.finished_at if dep.finished_at.tzinfo else dep.finished_at.replace(tzinfo=UTC)
        duration = max(0.0, (f - s).total_seconds())
    return DeploymentMetricsResponse(
        deployment_id=deployment_id,
        topology_id=dep.topology_id,
        project_id=topo.project_id if topo else None,
        status=dep.status.value,
        deploy_duration_seconds=duration,
        runtime_resources_count=int(cleanup.get("runtime_resources_count") or 0),
        active_terminal_sessions=int(cleanup.get("stale_terminal_sessions") or 0),
        cleanup_status=CleanupStatusMetrics(
            eligible_deployments=1 if cleanup.get("eligible_for_cleanup") else 0,
            deployments_with_runtime_resources=1 if int(cleanup.get("runtime_resources_count") or 0) > 0 else 0,
            stale_terminal_sessions=int(cleanup.get("stale_terminal_sessions") or 0),
        ),
        recent_failed_operations=_recent_failed_operations(session, deployment_id=deployment_id),
    )
