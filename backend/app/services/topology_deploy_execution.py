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
from app.services.deployment_validation import validate_topology_for_deploy


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


def execute_topology_deploy(db: Session, user: User, topology_id: UUID) -> Deployment | JSONResponse:
    """Create and run a deployment for ``topology_id``; same semantics as ``POST /topologies/{id}/deploy``."""
    topo = _topology_for_deploy(db, user, topology_id)
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

    deployment.started_at = datetime.now(UTC)
    _append_event(db, deployment.id, "Deployment pending — record created.")

    val_errors = validate_topology_for_deploy(topo)
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
        db.commit()
        loaded = _load_deployment_full(db, deployment.id)
        from app.schemas.deployment import DeploymentResponse

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=DeploymentResponse.model_validate(loaded).model_dump(mode="json"),
        )

    _append_event(db, deployment.id, "Topology validation passed.")

    deployment.status = DeploymentStatus.DEPLOYING
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

    deployment.status = DeploymentStatus.SUCCEEDED
    deployment.finished_at = datetime.now(UTC)
    if outcome.runtime_access:
        replace_runtime_resources_from_payload(db, deployment.id, outcome.runtime_access)
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
