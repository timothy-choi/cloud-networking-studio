"""Deployment cleanup policies and status (Step 53B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import Deployment, DeploymentEvent, DeploymentStatus
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.topology import Topology
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.services.deployment_service_exposure_service import mark_expired_exposures


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
    eligible = dep.status in (DeploymentStatus.FAILED, DeploymentStatus.STOPPED) or expired
    reasons: list[str] = []
    if dep.status == DeploymentStatus.FAILED:
        reasons.append("failed")
    if dep.status == DeploymentStatus.STOPPED:
        reasons.append("stopped")
    if expired:
        reasons.append("ttl_expired")
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
        "eligible_for_cleanup": eligible or resource_count > 0,
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
    """Best-effort runtime resource cleanup for a deployment."""
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    expire_stale_terminal_sessions(db)
    mark_expired_exposures(db, dep.id)
    provider = runtime_provider_for_topology(dep.runtime_target)
    rows = provider.destroy(topo.id, dep.id, project_id=topo.project_id)
    db.add(
        DeploymentEvent(
            deployment_id=dep.id,
            message="Manual cleanup invoked — runtime resources torn down (best-effort).",
        )
    )
    for _level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                message=msg,
            )
        )
    return {
        "ok": True,
        "deployment_id": str(dep.id),
        "events": [{"message": msg} for _level, msg in rows],
    }
