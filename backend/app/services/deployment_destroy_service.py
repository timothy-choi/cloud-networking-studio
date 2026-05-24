"""Destroy deployment runtime resources and mark deployment stopped."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_timeline import TimelineEventType
from app.models.topology import Topology
from app.models.user import User
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.services.audit_service import record_audit
from app.services.deployment_timeline_service import record_timeline_event


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


def destroy_deployment_record(
    db: Session,
    *,
    dep: Deployment,
    topo: Topology,
    actor: User | None,
    audit_action: str = "deployment.destroy",
    audit_metadata: dict | None = None,
) -> None:
    """Tear down provider resources and mark deployment stopped."""
    provider = runtime_provider_for_topology(dep.runtime_target)

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
            "Destroy requested: deployment already stopped; running label-based Docker cleanup.",
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

    rows = provider.destroy(topo.id, dep.id, project_id=topo.project_id)

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

    dep.status = DeploymentStatus.STOPPED
    dep.finished_at = datetime.now(UTC)
    if already_stopped:
        _append_event(
            db,
            dep.id,
            "Destroy idempotent: deployment was already stopped; cleanup events recorded.",
            DeploymentEventLevel.INFO,
        )
    else:
        _append_event(
            db,
            dep.id,
            "Deployment stopped — runtime resources destroyed (best-effort).",
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
        record_audit(
            db,
            action=audit_action,
            resource_type="deployment",
            resource_id=dep.id,
            project_id=topo.project_id,
            actor_user_id=actor.id,
            status="success",
            metadata=audit_metadata,
        )
