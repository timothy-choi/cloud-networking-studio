"""Deployment orchestration routes — persistence + runtime provider execution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from starlette.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.models.user import User
from app.services.access_control import get_deployment_for_user, require_deployment_editor, require_topology_editor
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.schemas.deployment import DeploymentEventResponse, DeploymentResponse
from app.schemas.runtime import (
    RuntimeDeploymentResponse,
    RuntimeDeploymentSectionResponse,
    RuntimeDeploymentServicesSectionResponse,
    RuntimeInstructionsOnlyResponse,
    RuntimeLogsBundleResponse,
)
from app.schemas.service_exposure import (
    ServiceExposureCreate,
    ServiceExposureListResponse,
    ServiceExposureResponse,
)
from app.services.deployment_service_exposure_service import DuplicateExposureError
from app.services import deployment_service_exposure_service as exposure_svc
from app.services import runtime_state_service as runtime_svc
from app.services.deployment_planner import build_deployment_plan
from app.services.deployment_queries import active_deployment_blocking_new_deploy
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.services.deployment_runtime_resource_service import (
    replace_runtime_resources_from_payload,
)
from app.services.deployment_validation import validate_topology_for_deploy
from app.runtime.go_runner_client import GoRunnerDeployError

router = APIRouter(tags=["deployments"])


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
    dep = require_deployment_editor(db, user, deployment_id)
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
    db.commit()

    return _load_deployment_full(db, deployment_id)


def _deployment_runtime_snapshot(db: Session, deployment_id: UUID) -> RuntimeDeploymentResponse:
    try:
        return runtime_svc.build_deployment_runtime(
            db,
            deployment_id,
            emit_inspection_event=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None


@router.get(
    "/deployments/{deployment_id}/runtime/logs",
    response_model=RuntimeLogsBundleResponse,
    summary="Deployment runtime log pointers",
)
def get_deployment_runtime_logs(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeLogsBundleResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_logs_bundle(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/nodes",
    response_model=RuntimeDeploymentSectionResponse,
    summary="Persisted runtime node resources for a deployment",
)
def get_deployment_runtime_nodes(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentSectionResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_nodes_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/services",
    response_model=RuntimeDeploymentServicesSectionResponse,
    summary="Persisted runtime service resources for a deployment",
)
def get_deployment_runtime_services(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentServicesSectionResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_services_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/exposures",
    response_model=ServiceExposureListResponse,
    summary="List service exposure records for a deployment",
)
def list_service_exposures(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceExposureListResponse:
    get_deployment_for_user(db, user, deployment_id)
    rows = exposure_svc.list_exposure_rows(db, deployment_id)
    db.commit()
    return ServiceExposureListResponse(
        deployment_id=deployment_id,
        exposures=[ServiceExposureResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/expose",
    response_model=ServiceExposureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Expose a persisted runtime service row",
    response_model_by_alias=True,
)
def expose_runtime_service(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payload: ServiceExposureCreate | None = Body(None),
) -> ServiceExposureResponse:
    dep = require_deployment_editor(db, user, deployment_id)
    try:
        row = exposure_svc.create_exposure(
            db,
            dep,
            service_id,
            ttl_hours=payload.ttl_hours if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    except DuplicateExposureError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active exposure already exists for this service resource.",
        ) from exc
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/deployments/{deployment_id}/runtime/services/{service_id}/expose",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an active service exposure",
)
def unexpose_runtime_service(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    dep = require_deployment_editor(db, user, deployment_id)
    try:
        ok = exposure_svc.remove_exposure(db, dep, service_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active exposure for this service resource.",
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/deployments/{deployment_id}/runtime/instructions",
    response_model=RuntimeInstructionsOnlyResponse,
    summary="Integration instructions for using this deployment",
)
def get_deployment_runtime_instructions(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeInstructionsOnlyResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_instructions_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime",
    response_model=RuntimeDeploymentResponse,
    summary="Deployment runtime snapshot",
)
def get_deployment_runtime(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentResponse:
    get_deployment_for_user(db, user, deployment_id)
    body = _deployment_runtime_snapshot(db, deployment_id)
    db.commit()
    return body


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
