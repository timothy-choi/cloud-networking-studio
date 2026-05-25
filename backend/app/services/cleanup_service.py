"""Deployment cleanup policies and status (Step 53B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import (
    Deployment,
    DeploymentCleanupStatus,
    DeploymentEvent,
    DeploymentEventLevel,
    DeploymentStatus,
    TopologySyncStatus,
)
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.deployment_timeline import TimelineEventType
from app.models.topology import Topology
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.services.deployment_destroy_service import (
    _close_terminal_sessions_for_deployment,
    _collect_remaining_resources,
    _format_remaining_resources,
    _has_remaining_resources,
    _legacy_node_ids_from_deployment,
    _revoke_exposures_for_deployment,
)
from app.services.deployment_service_exposure_service import mark_expired_exposures
from app.services.deployment_timeline_service import record_timeline_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


def deployment_expires_at(dep: Deployment) -> datetime | None:
    ttl = int(settings.deployment_ttl_hours or 0)
    if ttl <= 0:
        return None
    base = dep.started_at or dep.created_at
    if base is None:
        return None
    return base + timedelta(hours=ttl)


def is_deployment_expired(dep: Deployment, *, now: datetime | None = None) -> bool:
    exp = deployment_expires_at(dep)
    if exp is None:
        return False
    return (now or _utc_now()) >= exp


def expire_stale_terminal_sessions(db: Session, *, now: datetime | None = None) -> int:
    """Mark idle/expired terminal sessions closed (best-effort)."""
    now = now or _utc_now()
    idle_cutoff = now - timedelta(seconds=max(60, settings.terminal_idle_timeout_seconds))
    max_cutoff = now - timedelta(seconds=max(120, settings.terminal_max_duration_seconds))
    rows = list(
        db.scalars(
            select(DeploymentRuntimeTerminalSession).where(
                DeploymentRuntimeTerminalSession.status.in_(("opening", "active"))
            )
        ).all()
    )
    closed = 0
    for sess in rows:
        reason: str | None = None
        if sess.opened_at and sess.opened_at <= max_cutoff:
            reason = "max_duration"
        elif sess.last_activity_at and sess.last_activity_at <= idle_cutoff:
            reason = "idle_timeout"
        elif sess.opened_at and sess.opened_at <= idle_cutoff and sess.last_activity_at is None:
            reason = "idle_timeout"
        if reason:
            sess.status = "closed"
            sess.closed_at = now
            sess.close_reason = reason
            closed += 1
    if closed:
        db.flush()
    return closed


def _deployment_eligible_for_cleanup(dep: Deployment, resource_count: int, expired: bool) -> bool:
    if dep.cleanup_status == DeploymentCleanupStatus.CLEAN and dep.status == DeploymentStatus.STOPPED:
        return False
    if dep.status == DeploymentStatus.SUCCEEDED:
        return True
    if dep.status in (DeploymentStatus.FAILED, DeploymentStatus.STOPPING):
        return True
    if dep.status == DeploymentStatus.STOPPED and dep.cleanup_status != DeploymentCleanupStatus.CLEAN:
        return True
    if expired or resource_count > 0:
        return True
    return False


def build_cleanup_status(db: Session, deployment_id: UUID) -> dict[str, Any]:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    mark_expired_exposures(db, deployment_id)
    expire_stale_terminal_sessions(db)
    resource_count = int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeResource)
            .where(DeploymentRuntimeResource.deployment_id == deployment_id)
        )
        or 0
    )
    stale_terminals = int(
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
    exp = deployment_expires_at(dep)
    expired = is_deployment_expired(dep)
    eligible = _deployment_eligible_for_cleanup(dep, resource_count, expired)
    reasons: list[str] = []
    if dep.status == DeploymentStatus.FAILED:
        reasons.append("failed")
    if dep.status == DeploymentStatus.STOPPED:
        reasons.append("stopped")
    if dep.status == DeploymentStatus.SUCCEEDED:
        reasons.append("active")
    if expired:
        reasons.append("ttl_expired")
    if resource_count > 0:
        reasons.append("runtime_resources")
    if dep.cleanup_status == DeploymentCleanupStatus.PARTIAL_FAILED:
        reasons.append("partial_cleanup")
    last_cleanup = db.scalar(
        select(DeploymentEvent.created_at)
        .where(
            DeploymentEvent.deployment_id == deployment_id,
            DeploymentEvent.message.ilike("%cleanup%"),
        )
        .order_by(DeploymentEvent.created_at.desc())
        .limit(1)
    )
    return {
        "deployment_id": str(deployment_id),
        "status": dep.status.value,
        "cleanup_status": dep.cleanup_status.value,
        "eligible_for_cleanup": eligible,
        "reasons": reasons,
        "runtime_resources_count": resource_count,
        "stale_terminal_sessions": stale_terminals,
        "expires_at": exp.isoformat() if exp else None,
        "expired": expired,
        "deployment_ttl_hours": int(settings.deployment_ttl_hours or 0),
        "last_cleanup_at": last_cleanup.isoformat() if last_cleanup else None,
        "topology_id": str(dep.topology_id),
        "project_id": str(topo.project_id) if topo else None,
    }


def run_deployment_cleanup(db: Session, dep: Deployment) -> dict[str, Any]:
    """Tear down runtime resources and reconcile deployment DB state."""
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")

    already_clean = (
        dep.status == DeploymentStatus.STOPPED
        and dep.cleanup_status == DeploymentCleanupStatus.CLEAN
    )

    record_timeline_event(
        db,
        deployment_id=dep.id,
        event_type=TimelineEventType.CLEANUP_REQUESTED,
        message="Cleanup requested.",
        status="info",
    )
    record_timeline_event(
        db,
        deployment_id=dep.id,
        event_type=TimelineEventType.CLEANUP_STARTED,
        message="Cleanup started — tearing down runtime resources.",
        status="running",
    )
    db.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message="Manual cleanup invoked — reconciling runtime resources and deployment state.",
        )
    )

    expire_stale_terminal_sessions(db)
    mark_expired_exposures(db, dep.id)
    closed_terminals = _close_terminal_sessions_for_deployment(db, dep.id)
    if closed_terminals:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message=f"Closed {closed_terminals} active terminal session(s) during cleanup.",
            )
        )
    revoked_exposures = _revoke_exposures_for_deployment(db, dep.id)
    if revoked_exposures:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.INFO,
                message=f"Revoked {revoked_exposures} active service exposure(s) during cleanup.",
            )
        )

    legacy_node_ids = _legacy_node_ids_from_deployment(dep)
    provider = runtime_provider_for_topology(dep.runtime_target)
    rows = provider.destroy(
        topo.id,
        dep.id,
        project_id=topo.project_id,
        legacy_node_ids=legacy_node_ids or None,
    )

    db.execute(
        delete(DeploymentRuntimeResource).where(
            DeploymentRuntimeResource.deployment_id == dep.id
        )
    )

    event_payloads: list[dict[str, str]] = []
    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=level,
                message=msg,
            )
        )
        event_payloads.append({"message": msg})

    remaining = _collect_remaining_resources(
        db,
        provider=provider,
        topo=topo,
        dep=dep,
        legacy_node_ids=legacy_node_ids,
    )
    has_remaining = _has_remaining_resources(remaining)
    marked_destroyed = False

    if has_remaining:
        dep.cleanup_status = DeploymentCleanupStatus.PARTIAL_FAILED
        summary = _format_remaining_resources(remaining)
        message = "Cleanup partially completed; some resources remain."
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=f"Cleanup partial failure; remaining resources: {summary}",
            )
        )
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.CLEANUP_PARTIAL_FAILED,
            message=f"Cleanup partially completed: {summary}",
            status="warning",
            metadata={"remaining_resources": remaining},
        )
    else:
        dep.cleanup_status = DeploymentCleanupStatus.CLEAN
        if not already_clean:
            if dep.status != DeploymentStatus.STOPPED:
                dep.status = DeploymentStatus.STOPPED
                dep.finished_at = _utc_now()
                marked_destroyed = True
            dep.topology_sync_status = TopologySyncStatus.OUT_OF_SYNC
            db.add(
                DeploymentEvent(
                    deployment_id=dep.id,
                    level=DeploymentEventLevel.INFO,
                    message="Cleanup completed — deployment marked stopped; runtime resources removed.",
                )
            )
            record_timeline_event(
                db,
                deployment_id=dep.id,
                event_type=TimelineEventType.DEPLOYMENT_MARKED_DESTROYED_AFTER_CLEANUP,
                message="Deployment marked stopped after cleanup removed all runtime resources.",
                status="succeeded",
            )
            message = "Cleanup completed; deployment marked destroyed."
        else:
            message = "Cleanup completed (deployment already clean)."
            db.add(
                DeploymentEvent(
                    deployment_id=dep.id,
                    level=DeploymentEventLevel.INFO,
                    message="Cleanup idempotent: deployment already stopped and clean.",
                )
            )
        record_timeline_event(
            db,
            deployment_id=dep.id,
            event_type=TimelineEventType.CLEANUP_SUCCEEDED,
            message=message,
            status="succeeded",
        )

    db.flush()
    return {
        "ok": not has_remaining,
        "partial": has_remaining,
        "deployment_id": str(dep.id),
        "cleanup_status": dep.cleanup_status.value,
        "deployment_status": dep.status.value,
        "message": message,
        "marked_destroyed": marked_destroyed,
        "remaining_resources": remaining if has_remaining else {},
        "events": event_payloads,
    }
