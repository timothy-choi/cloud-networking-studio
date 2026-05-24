"""Destroy deployment runtime resources and mark deployment stopped."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.deployment import (
    Deployment,
    DeploymentCleanupStatus,
    DeploymentEvent,
    DeploymentEventLevel,
    DeploymentStatus,
)
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.deployment_service_exposure import DeploymentServiceExposure
from app.models.deployment_timeline import TimelineEventType
from app.models.topology import Topology
from app.models.user import User
from app.providers.docker_runtime_provider import (
    DockerRuntimeProvider,
    fake_remaining_containers,
    remaining_labeled_runtime_resources,
    runtime_provider_for_topology,
)
from app.services.audit_service import record_audit
from app.services.deployment_timeline_service import record_timeline_event


@dataclass
class DestroyResult:
    cleanup_status: DeploymentCleanupStatus
    remaining_resources: dict[str, Any] = field(default_factory=dict)


def _append_event(
    db: Session,
    deployment_id: UUID,
    message: str,
    level: DeploymentEventLevel = DeploymentEventLevel.INFO,
) -> None:
    db.add(
        DeploymentEvent(
            deployment_id=deployment_id,
            level=level,
            message=message,
        )
    )


def _legacy_node_ids_from_deployment(dep: Deployment) -> frozenset[UUID]:
    eff = dep.effective_config_json or {}
    out: set[UUID] = set()
    for raw in eff.get("nodes") or []:
        node_id = raw.get("id")
        if not node_id:
            continue
        try:
            out.add(UUID(str(node_id)))
        except ValueError:
            continue
    return frozenset(out)


def _close_terminal_sessions_for_deployment(db: Session, deployment_id: UUID) -> int:
    now = datetime.now(UTC)
    rows = list(
        db.scalars(
            select(DeploymentRuntimeTerminalSession).where(
                DeploymentRuntimeTerminalSession.deployment_id == deployment_id,
                DeploymentRuntimeTerminalSession.status.in_(("opening", "active")),
            )
        ).all()
    )
    for sess in rows:
        sess.status = "closed"
        sess.closed_at = now
        sess.close_reason = "deployment_destroy"
    if rows:
        db.flush()
    return len(rows)


def _revoke_exposures_for_deployment(db: Session, deployment_id: UUID) -> int:
    now = datetime.now(UTC)
    result = db.execute(
        update(DeploymentServiceExposure)
        .where(
            DeploymentServiceExposure.deployment_id == deployment_id,
            DeploymentServiceExposure.status == "active",
        )
        .values(status="removed", updated_at=now)
    )
    if result.rowcount:
        db.flush()
    return int(result.rowcount or 0)


def _count_db_runtime_resources(db: Session, deployment_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeResource)
            .where(DeploymentRuntimeResource.deployment_id == deployment_id)
        )
        or 0
    )


def _count_active_terminal_sessions(db: Session, deployment_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeTerminalSession)
            .where(
                DeploymentRuntimeTerminalSession.deployment_id == deployment_id,
                DeploymentRuntimeTerminalSession.status.in_(("opening", "active")),
            )
        )
        or 0
    )


def _count_active_exposures(db: Session, deployment_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentServiceExposure)
            .where(
                DeploymentServiceExposure.deployment_id == deployment_id,
                DeploymentServiceExposure.status == "active",
            )
        )
        or 0
    )


def _engine_remaining_resources(
    provider: object,
    *,
    topo: Topology,
    dep: Deployment,
    legacy_node_ids: frozenset[UUID],
) -> dict[str, list[str]]:
    if isinstance(provider, DockerRuntimeProvider):
        return remaining_labeled_runtime_resources(
            provider._client,
            topo.id,
            dep.id,
            legacy_node_ids=legacy_node_ids,
        )
    remaining = sorted(fake_remaining_containers(dep.id))
    if remaining:
        return {"containers": remaining, "networks": []}
    return {"containers": [], "networks": []}


def _collect_remaining_resources(
    db: Session,
    *,
    provider: object,
    topo: Topology,
    dep: Deployment,
    legacy_node_ids: frozenset[UUID],
) -> dict[str, Any]:
    engine = _engine_remaining_resources(
        provider,
        topo=topo,
        dep=dep,
        legacy_node_ids=legacy_node_ids,
    )
    return {
        "containers": list(engine.get("containers") or []),
        "networks": list(engine.get("networks") or []),
        "runtime_resources": _count_db_runtime_resources(db, dep.id),
        "terminal_sessions": _count_active_terminal_sessions(db, dep.id),
        "exposures": _count_active_exposures(db, dep.id),
    }


def _has_remaining_resources(remaining: dict[str, Any]) -> bool:
    if remaining.get("containers") or remaining.get("networks"):
        return True
    for key in ("runtime_resources", "terminal_sessions", "exposures"):
        if int(remaining.get(key) or 0) > 0:
            return True
    return False


def _format_remaining_resources(remaining: dict[str, Any]) -> str:
    parts: list[str] = []
    containers = remaining.get("containers") or []
    if containers:
        parts.append(f"containers={', '.join(containers)}")
    networks = remaining.get("networks") or []
    if networks:
        parts.append(f"networks={', '.join(networks)}")
    if int(remaining.get("runtime_resources") or 0) > 0:
        parts.append(f"runtime_resources={remaining['runtime_resources']}")
    if int(remaining.get("terminal_sessions") or 0) > 0:
        parts.append(f"terminal_sessions={remaining['terminal_sessions']}")
    if int(remaining.get("exposures") or 0) > 0:
        parts.append(f"exposures={remaining['exposures']}")
    return "; ".join(parts) if parts else "none"


def destroy_deployment_record(
    db: Session,
    *,
    dep: Deployment,
    topo: Topology,
    actor: User | None,
    audit_action: str = "deployment.destroy",
    audit_metadata: dict | None = None,
) -> DestroyResult:
    """Tear down all provider/DB resources for a deployment, then mark it stopped."""
    provider = runtime_provider_for_topology(dep.runtime_target)
    legacy_node_ids = _legacy_node_ids_from_deployment(dep)

    record_timeline_event(
        db,
        deployment_id=dep.id,
        event_type=TimelineEventType.DESTROY_REQUESTED,
        message="Destroy requested.",
        status="info",
    )
    if actor is not None:
        meta = dict(audit_metadata or {})
        record_audit(
            db,
            action=audit_action,
            resource_type="deployment",
            resource_id=dep.id,
            project_id=topo.project_id,
            actor_user_id=actor.id,
            status="pending",
            metadata=meta or None,
        )

    already_stopped = dep.status == DeploymentStatus.STOPPED
    if already_stopped:
        _append_event(
            db,
            dep.id,
            "Destroy requested: deployment already stopped; running full label-based cleanup.",
            DeploymentEventLevel.INFO,
        )
    else:
        dep.status = DeploymentStatus.STOPPING
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.DESTROY_STARTED,
            message="Destroy started — tearing down runtime resources.",
            status="running",
        )
        _append_event(db, dep.id, "Deployment stopping — tearing down runtime resources.")
        db.flush()

    closed_terminals = _close_terminal_sessions_for_deployment(db, dep.id)
    if closed_terminals:
        _append_event(
            db,
            dep.id,
            f"Closed {closed_terminals} active terminal session(s) for deployment destroy.",
        )

    revoked_exposures = _revoke_exposures_for_deployment(db, dep.id)
    if revoked_exposures:
        _append_event(
            db,
            dep.id,
            f"Revoked {revoked_exposures} active service exposure(s) for deployment destroy.",
        )

    rows = provider.destroy(
        topo.id,
        dep.id,
        project_id=topo.project_id,
        legacy_node_ids=legacy_node_ids,
    )

    db.execute(
        delete(DeploymentRuntimeResource).where(
            DeploymentRuntimeResource.deployment_id == dep.id
        )
    )

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=level,
                message=msg,
            )
        )

    remaining = _collect_remaining_resources(
        db,
        provider=provider,
        topo=topo,
        dep=dep,
        legacy_node_ids=legacy_node_ids,
    )
    cleanup_status = (
        DeploymentCleanupStatus.PARTIAL_FAILED
        if _has_remaining_resources(remaining)
        else DeploymentCleanupStatus.CLEAN
    )
    dep.cleanup_status = cleanup_status
    dep.status = DeploymentStatus.STOPPED
    dep.finished_at = datetime.now(UTC)

    if cleanup_status == DeploymentCleanupStatus.PARTIAL_FAILED:
        summary = _format_remaining_resources(remaining)
        _append_event(
            db,
            dep.id,
            f"Deployment stopped with partial cleanup failure; remaining resources: {summary}",
            DeploymentEventLevel.WARNING,
        )
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.DESTROY_SUCCEEDED,
            message=f"Destroy completed with partial cleanup failure: {summary}",
            status="warning",
        )
    elif already_stopped:
        _append_event(
            db,
            dep.id,
            "Destroy idempotent: deployment was already stopped; cleanup completed.",
            DeploymentEventLevel.INFO,
        )
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.DESTROY_SUCCEEDED,
            message="Destroy succeeded.",
            status="succeeded",
        )
    else:
        _append_event(
            db,
            dep.id,
            "Deployment stopped — runtime resources destroyed.",
            DeploymentEventLevel.INFO,
        )
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.DESTROY_SUCCEEDED,
            message="Destroy succeeded.",
            status="succeeded",
        )

    if actor is not None:
        final_meta = dict(audit_metadata or {})
        final_meta["cleanup_status"] = cleanup_status.value
        if _has_remaining_resources(remaining):
            final_meta["remaining_resources"] = remaining
        record_audit(
            db,
            action=audit_action,
            resource_type="deployment",
            resource_id=dep.id,
            project_id=topo.project_id,
            actor_user_id=actor.id,
            status="success" if cleanup_status == DeploymentCleanupStatus.CLEAN else "warning",
            metadata=final_meta,
        )

    return DestroyResult(cleanup_status=cleanup_status, remaining_resources=remaining)
