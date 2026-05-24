"""Shared topology → deployment execution (used by HTTP route and onboarding demo)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus, TopologySyncStatus
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
from app.services.node_runtime_config import validate_deploy_node_images_from_snapshot
from app.services.quota_service import ensure_can_deploy_project, ensure_topology_node_quota
from app.core.config import settings
from app.core.secret_masking import scrub_sensitive_dict
from app.services.rate_limit_service import check_rate_limit
from app.services.effective_config_service import build_effective_config, effective_config_summary
from app.services import deployment_profile_service as profile_svc
from app.services import topology_version_service as version_svc


def _notify_deploy_outcome(
    db: Session,
    *,
    user: User,
    topo: Topology,
    deployment: Deployment,
    succeeded: bool,
    reason: str | None = None,
) -> None:
    try:
        from app.services.notification_service import notify_deployment_outcome

        notify_deployment_outcome(
            db,
            user_id=user.id,
            project_id=topo.project_id,
            topology_id=topo.id,
            deployment_id=deployment.id,
            topology_name=topo.name,
            succeeded=succeeded,
            reason=reason,
        )
    except Exception:
        pass


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


def _notify_prod_like_deploy(
    db: Session,
    *,
    topo: Topology,
    user: User,
    deployment: Deployment,
    profile_name: str,
    event: str,
    reason: str | None = None,
) -> None:
    try:
        from app.services.notification_service import notify_project_owners

        body = f"Prod-like deployment {event} for topology '{topo.name}' (profile: {profile_name})."
        if reason:
            body += f" Reason: {reason}"
        notify_project_owners(
            db,
            topo.project_id,
            type="deployment.prod_like",
            title=f"Prod-like deploy {event}: {topo.name}",
            message=body,
            severity="warning" if event == "failed" else "info",
            metadata=scrub_sensitive_dict(
                {
                    "topology_id": str(topo.id),
                    "deployment_id": str(deployment.id),
                    "event": event,
                }
            ),
        )
    except Exception:
        pass


def execute_topology_deploy(
    db: Session,
    user: User,
    topology_id: UUID,
    *,
    network_allocation_mode: str | None = None,
    profile_id: UUID | None = None,
    topology_version_id: UUID | None = None,
) -> Deployment | JSONResponse:
    """Create and run a deployment for ``topology_id``; same semantics as ``POST /topologies/{id}/deploy``."""
    topo = _topology_for_deploy(db, user, topology_id)
    ensure_can_deploy_project(db, topo.project_id, user_id=user.id)
    check_rate_limit(
        key=f"deploy:user:{user.id}",
        limit=settings.rate_limit_deploy_per_user,
        action="deploy_topology",
    )
    ensure_topology_node_quota(db, topology_id, adding=0, user_id=user.id, project_id=topo.project_id)
    alloc_mode = resolve_network_allocation_mode(topo, network_allocation_mode)

    profile = profile_svc.get_profile(db, topology_id, profile_id) if profile_id else None
    if profile_id and profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment profile not found")

    version_row = None
    base_snapshot = None
    if topology_version_id:
        version_row = version_svc.get_version_for_topology(db, topology_id, topology_version_id)
        if version_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topology version not found")
        base_snapshot = version_row.snapshot_json
    else:
        deploy_version = version_svc.create_topology_version(
            db,
            topology=topo,
            created_by=user,
            source="deploy",
            name="Deploy snapshot",
        )
        version_row = deploy_version
        base_snapshot = deploy_version.snapshot_json
        record_audit(
            db,
            action="topology.version.created",
            resource_type="topology_version",
            resource_id=deploy_version.id,
            project_id=topo.project_id,
            actor_user_id=user.id,
            status="success",
            metadata=scrub_sensitive_dict(
                {
                    "topology_id": str(topology_id),
                    "version_number": deploy_version.version_number,
                    "source": "deploy",
                }
            ),
        )

    effective = build_effective_config(
        snapshot=base_snapshot,
        profile=profile,
        network_allocation_mode=alloc_mode if network_allocation_mode is not None else None,
    )
    eff_runtime = (effective.get("topology") or {}).get("runtime_target") or topo.runtime_target

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
        runtime_target=eff_runtime,
        topology_version_id=version_row.id if version_row else None,
        deployment_profile_id=profile.id if profile else None,
        effective_config_json=scrub_sensitive_dict(effective),
        topology_sync_status=TopologySyncStatus.IN_SYNC,
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
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology_id),
                "topology_version_id": str(version_row.id) if version_row else None,
                "deployment_profile_id": str(profile.id) if profile else None,
                "profile_type": profile.profile_type if profile else None,
                "effective_summary": effective_config_summary(effective),
            }
        ),
    )

    if profile and profile.profile_type == "prod_like":
        _notify_prod_like_deploy(
            db,
            topo=topo,
            user=user,
            deployment=deployment,
            profile_name=profile.name,
            event="started",
        )

    deployment.started_at = datetime.now(UTC)
    _append_event(db, deployment.id, "Deployment pending — record created.")

    val_errors = validate_topology_for_deploy(topo, network_allocation_mode=alloc_mode)
    val_errors.extend(validate_deploy_node_images_from_snapshot(effective.get("nodes")))
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
        _notify_deploy_outcome(db, user=user, topo=topo, deployment=deployment, succeeded=False, reason=joined)
        if profile and profile.profile_type == "prod_like":
            _notify_prod_like_deploy(
                db,
                topo=topo,
                user=user,
                deployment=deployment,
                profile_name=profile.name,
                event="failed",
                reason=joined,
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
        metadata=scrub_sensitive_dict(
            {
                "topology_version_id": str(version_row.id) if version_row else None,
                "deployment_profile_id": str(profile.id) if profile else None,
                "profile_type": profile.profile_type if profile else None,
            }
        ),
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
        effective_config=effective,
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
        _notify_deploy_outcome(
            db, user=user, topo=topo, deployment=deployment, succeeded=False, reason=exc.message
        )
        if profile and profile.profile_type == "prod_like":
            _notify_prod_like_deploy(
                db,
                topo=topo,
                user=user,
                deployment=deployment,
                profile_name=profile.name,
                event="failed",
                reason=exc.message,
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
        _notify_deploy_outcome(db, user=user, topo=topo, deployment=deployment, succeeded=False, reason=str(exc))
        if profile and profile.profile_type == "prod_like":
            _notify_prod_like_deploy(
                db,
                topo=topo,
                user=user,
                deployment=deployment,
                profile_name=profile.name,
                event="failed",
                reason=str(exc),
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
    _notify_deploy_outcome(db, user=user, topo=topo, deployment=deployment, succeeded=True)
    if profile and profile.profile_type == "prod_like":
        _notify_prod_like_deploy(
            db,
            topo=topo,
            user=user,
            deployment=deployment,
            profile_name=profile.name,
            event="succeeded",
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
            _notify_deploy_outcome(db, user=user, topo=topo, deployment=deployment, succeeded=False, reason=msg)
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
