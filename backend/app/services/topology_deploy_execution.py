"""Shared topology → deployment execution (used by HTTP route and onboarding demo)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.models.user import User
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.runtime.go_runner_client import GoRunnerDeployError
from app.services.access_control import require_topology_editor
from app.services.deployment_planner import build_deployment_plan
from app.services.deployment_queries import active_deployment_blocking_new_deploy
from app.services.deployment_runtime_resource_service import (
    replace_runtime_resources_from_payload,
)
from app.services.network_allocation import (
    INTENT_UNSUPPORTED_RUNTIME_MESSAGE,
    is_intent_mode,
    merge_allocation_mode_into_config,
    resolve_network_allocation_mode,
)
from app.models.deployment_timeline import TimelineEventType
from app.services.audit_service import record_audit
from app.services.deployment_timeline_helpers import timeline_from_runner_message
from app.services.deployment_timeline_service import record_timeline_event
from app.services.deployment_validation import validate_topology_for_deploy
from app.services.quota_service import ensure_can_deploy_project, ensure_topology_node_quota
from app.core.config import settings
from app.services.rate_limit_service import check_rate_limit


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


def _load_deployment_full(db: Session, deployment_id: UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()


def _topology_for_deploy(db: Session, user: User, topology_id: UUID) -> Topology:
    require_topology_editor(db, user, topology_id)
    stmt = (
        select(Topology)
        .where(Topology.id == topology_id)
        .options(
            selectinload(Topology.nodes),
            selectinload(Topology.links),
        )
    )
    return db.execute(stmt).scalar_one()


def execute_topology_deploy(
    db: Session,
    user: User,
    topology_id: UUID,
    *,
    network_allocation_mode: str | None = None,
) -> Deployment | JSONResponse:
    """Create and run a deployment for ``topology_id``; same semantics as ``POST /topologies/{id}/deploy``."""
    topo = _topology_for_deploy(db, user, topology_id)
    ensure_can_deploy_project(db, topo.project_id)
    check_rate_limit(
        key=f"deploy:user:{user.id}",
        limit=settings.rate_limit_deploy_per_user,
        action="deploy_topology",
    )
    ensure_topology_node_quota(db, topology_id, adding=0)
    alloc_mode = resolve_network_allocation_mode(topo, network_allocation_mode)
    if network_allocation_mode is not None:
        topo.config = merge_allocation_mode_into_config(topo.config, alloc_mode)
        db.flush()

    provider = runtime_provider_for_topology(topo.runtime_target)

    blocker = active_deployment_blocking_new_deploy(db, topology_id)
    if blocker is not None:
        _append_event(
            db,
            blocker.id,
            (
                "Duplicate deployment rejected: this topology already has an active deployment "
                f"({blocker.id}, status={blocker.status.value}). Destroy it before starting a new deploy."
            ),
            DeploymentEventLevel.WARNING,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An active deployment already exists for this topology "
                f"(deployment_id={blocker.id}, status={blocker.status.value}). "
                "POST /deployments/{id}/destroy to tear down runtime resources, then deploy again."
            ),
        )

    deployment = Deployment(
        topology_id=topology_id,
        status=DeploymentStatus.PENDING,
        runtime_target=topo.runtime_target,
    )
    db.add(deployment)
    db.flush()

    record_timeline_event(
        db,
        deployment_id=deployment.id,
        event_type=TimelineEventType.DEPLOY_REQUESTED,
        message="Deployment requested.",
        status="info",
    )
    record_audit(
        db,
        action="topology.deploy",
        resource_type="deployment",
        resource_id=deployment.id,
        project_id=topo.project_id,
        actor_user_id=user.id,
        status="pending",
        metadata={"topology_id": str(topology_id)},
    )

    deployment.started_at = datetime.now(UTC)
    _append_event(db, deployment.id, "Deployment pending — record created.")

    val_errors = validate_topology_for_deploy(topo, network_allocation_mode=alloc_mode)
    rt = (topo.runtime_target or "").lower().strip()
    if is_intent_mode(alloc_mode) and rt != "docker":
        val_errors.append(INTENT_UNSUPPORTED_RUNTIME_MESSAGE)
    if val_errors:
        joined = "; ".join(val_errors)
        _append_event(
            db,
            deployment.id,
            f"Topology validation failed: {joined}",
            DeploymentEventLevel.ERROR,
        )
        deployment.status = DeploymentStatus.FAILED
        deployment.finished_at = datetime.now(UTC)
        record_timeline_event(
            db,
            deployment_id=deployment.id,
            event_type=TimelineEventType.DEPLOY_FAILED,
            message=f"Topology validation failed: {joined}",
            status="failed",
            metadata={"errors": val_errors},
        )
        record_audit(
            db,
            action="topology.deploy",
            resource_type="deployment",
            resource_id=deployment.id,
            project_id=topo.project_id,
            actor_user_id=user.id,
            status="failure",
            metadata={"reason": "validation_failed"},
        )
        db.commit()
        loaded = _load_deployment_full(db, deployment.id)
        from app.schemas.deployment import DeploymentResponse

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=DeploymentResponse.model_validate(loaded).model_dump(mode="json"),
        )

    _append_event(db, deployment.id, "Topology validation passed.")

    deployment.status = DeploymentStatus.DEPLOYING
    record_timeline_event(
        db,
        deployment_id=deployment.id,
        event_type=TimelineEventType.DEPLOY_STARTED,
        message="Deployment started — invoking runtime provider.",
        status="running",
    )
    _append_event(
        db,
        deployment.id,
        "Deployment deploying — invoking runtime provider.",
    )
    db.flush()

    plan = build_deployment_plan(
        topo,
        deployment_id=deployment.id,
        requested_by_user_id=user.id,
        network_allocation_mode=alloc_mode,
    )

    try:
        outcome = provider.deploy(plan)
    except GoRunnerDeployError as exc:
        deployment.status = DeploymentStatus.FAILED
        deployment.finished_at = datetime.now(UTC)
        _append_event(
            db,
            deployment.id,
            "Partial failure cleanup started (best-effort Docker rollback).",
            DeploymentEventLevel.WARNING,
        )
        _append_event(
            db,
            deployment.id,
            "Partial failure cleanup completed (best-effort).",
            DeploymentEventLevel.INFO,
        )
        for level, msg in exc.events:
            db.add(
                DeploymentEvent(
                    deployment_id=deployment.id,
                    level=level,
                    message=msg,
                )
            )
            timeline_from_runner_message(db, deployment_id=deployment.id, message=msg)
        record_timeline_event(
            db,
            deployment_id=deployment.id,
            event_type=TimelineEventType.DEPLOY_FAILED,
            message=f"Deployment failed: {exc.message}",
            status="failed",
            metadata={"error": exc.message},
        )
        record_audit(
            db,
            action="topology.deploy",
            resource_type="deployment",
            resource_id=deployment.id,
            project_id=topo.project_id,
            actor_user_id=user.id,
            status="failure",
            metadata={"error": exc.message},
        )
        _append_event(
            db,
            deployment.id,
            f"Deployment failed: {exc.message}",
            DeploymentEventLevel.ERROR,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        ) from exc
    except Exception as exc:
        deployment.status = DeploymentStatus.FAILED
        deployment.finished_at = datetime.now(UTC)
        _append_event(
            db,
            deployment.id,
            "Partial failure cleanup started (best-effort Docker rollback).",
            DeploymentEventLevel.WARNING,
        )
        _append_event(
            db,
            deployment.id,
            "Partial failure cleanup completed (best-effort).",
            DeploymentEventLevel.INFO,
        )
        _append_event(
            db,
            deployment.id,
            f"Deployment failed: {exc}",
            DeploymentEventLevel.ERROR,
        )
        record_timeline_event(
            db,
            deployment_id=deployment.id,
            event_type=TimelineEventType.DEPLOY_FAILED,
            message=f"Deployment failed: {exc}",
            status="failed",
        )
        record_audit(
            db,
            action="topology.deploy",
            resource_type="deployment",
            resource_id=deployment.id,
            project_id=topo.project_id,
            actor_user_id=user.id,
            status="failure",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    rows = outcome.events

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level=level,
                message=msg,
            )
        )
        timeline_from_runner_message(db, deployment_id=deployment.id, message=msg)

    deployment.status = DeploymentStatus.SUCCEEDED
    deployment.finished_at = datetime.now(UTC)
    record_timeline_event(
        db,
        deployment_id=deployment.id,
        event_type=TimelineEventType.DEPLOY_SUCCEEDED,
        message="Deployment succeeded.",
        status="succeeded",
    )
    record_audit(
        db,
        action="topology.deploy",
        resource_type="deployment",
        resource_id=deployment.id,
        project_id=topo.project_id,
        actor_user_id=user.id,
        status="success",
    )
    if outcome.runtime_access:
        resources = outcome.runtime_access.get("resources") or []
        service_count = sum(
            1
            for row in resources
            if isinstance(row, dict) and str(row.get("type") or "").strip() == "service"
        )
        if service_count > settings.quota_max_services_per_deployment:
            deployment.status = DeploymentStatus.FAILED
            deployment.finished_at = datetime.now(UTC)
            msg = (
                f"Deployment failed: service quota exceeded "
                f"({service_count}/{settings.quota_max_services_per_deployment})."
            )
            _append_event(db, deployment.id, msg, DeploymentEventLevel.ERROR)
            record_timeline_event(
                db,
                deployment_id=deployment.id,
                event_type=TimelineEventType.DEPLOY_FAILED,
                message=msg,
                status="failed",
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                "code": "QUOTA_EXCEEDED",
                "message": msg,
                "quota": "services_per_deployment",
                "used": service_count,
                "limit": settings.quota_max_services_per_deployment,
            })
        replace_runtime_resources_from_payload(
            db, deployment.id, outcome.runtime_access
        )
    prior_stopped = db.scalar(
        select(func.count())
        .select_from(Deployment)
        .where(
            Deployment.topology_id == topology_id,
            Deployment.id != deployment.id,
            Deployment.status == DeploymentStatus.STOPPED,
        )
    )
    if prior_stopped and int(prior_stopped) > 0:
        _append_event(
            db,
            deployment.id,
            "Redeploy allowed after stopped — new deployment succeeded.",
        )
    db.commit()

    return _load_deployment_full(db, deployment.id)
