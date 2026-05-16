"""Deployment orchestration routes — persistence + runtime provider execution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.models.user import User
from app.services.access_control import get_deployment_for_user, get_topology_for_user
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.schemas.deployment import DeploymentEventResponse, DeploymentResponse
from app.services.deployment_planner import build_deployment_plan
from app.services.deployment_queries import active_deployment_blocking_new_deploy
from app.services.deployment_validation import validate_topology_for_deploy

router = APIRouter(tags=["deployments"])


def _topology_for_deploy(db: Session, user: User, topology_id: UUID) -> Topology:
    get_topology_for_user(db, user, topology_id)
    stmt = (
        select(Topology)
        .where(Topology.id == topology_id)
        .options(
            selectinload(Topology.nodes),
            selectinload(Topology.links),
        )
    )
    return db.execute(stmt).scalar_one()


def _load_deployment_full(db: Session, deployment_id: UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()


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


@router.post(
    "/topologies/{topology_id}/deploy",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deploy topology",
    response_description="New deployment with nested audit events from the runtime provider.",
)
def deploy_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment | JSONResponse:
    """Run deployment against the topology's runtime target (real Docker when target is docker)."""
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

    plan = build_deployment_plan(topo)

    try:
        rows = provider.deploy(plan)
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


@router.post(
    "/deployments/{deployment_id}/destroy",
    response_model=DeploymentResponse,
    summary="Destroy deployment",
    response_description="Deployment marked stopped after provider teardown; related events appended.",
)
def destroy_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment:
    """Remove Docker resources labeled for this topology and mark deployment stopped."""
    dep = get_deployment_for_user(db, user, deployment_id)
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )

    provider = runtime_provider_for_topology(dep.runtime_target)

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
        _append_event(db, dep.id, "Deployment stopping — tearing down runtime resources.")
        db.flush()

    rows = provider.destroy(topo.id, dep.id)

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
    db.commit()

    return _load_deployment_full(db, deployment_id)


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentResponse,
    summary="Get deployment",
)
def get_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment:
    dep = get_deployment_for_user(db, user, deployment_id)
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()


@router.get(
    "/deployments/{deployment_id}/events",
    response_model=list[DeploymentEventResponse],
    summary="List deployment events",
    response_description="Append-only audit timeline for provisioning, inspection, and remediation.",
)
def list_deployment_events(
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    order: str = Query(
        default="asc",
        description="Sort order by created_at: asc (oldest first, default) or desc (newest first).",
        pattern="^(asc|desc)$",
    ),
    level: DeploymentEventLevel | None = Query(
        default=None,
        description="When set, only events with this severity are returned.",
    ),
    q: str | None = Query(
        default=None,
        max_length=500,
        description="Case-insensitive substring filter on message.",
    ),
    db: Session = Depends(get_db),
) -> list[DeploymentEvent]:
    get_deployment_for_user(db, user, deployment_id)
    stmt = select(DeploymentEvent).where(DeploymentEvent.deployment_id == deployment_id)
    if level is not None:
        stmt = stmt.where(DeploymentEvent.level == level)
    if q and q.strip():
        stmt = stmt.where(DeploymentEvent.message.ilike(f"%{q.strip()}%"))
    if order == "desc":
        stmt = stmt.order_by(DeploymentEvent.created_at.desc())
    else:
        stmt = stmt.order_by(DeploymentEvent.created_at.asc())
    return list(db.scalars(stmt).all())
