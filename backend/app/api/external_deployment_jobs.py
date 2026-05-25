"""External deployment job API routes (Step 57A)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.external_deployment_job import (
    ENABLED_JOB_MODES,
    ExternalDeploymentJobCreate,
    ExternalDeploymentJobListResponse,
    ExternalDeploymentJobLogsResponse,
    ExternalDeploymentJobResponse,
)
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services import deployment_target_service as target_svc
from app.services import external_deployment_job_service as job_svc

router = APIRouter(tags=["external-deployment-jobs"])


def _to_response(job) -> ExternalDeploymentJobResponse:
    return ExternalDeploymentJobResponse(
        id=str(job.id),
        project_id=str(job.project_id),
        topology_id=str(job.topology_id),
        target_id=str(job.target_id),
        mode=job.mode,
        status=job.status,
        logs=job.logs,
        artifact_refs=job.artifact_refs or [],
        created_by_user_id=str(job.created_by_user_id) if job.created_by_user_id else None,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _get_job_for_user(db: Session, user: User, job_id: UUID):
    job = job_svc.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Not found")
    get_topology_for_user(db, user, job.topology_id)
    return job


@router.get(
    "/topologies/{topology_id}/external-deployment-jobs",
    response_model=ExternalDeploymentJobListResponse,
)
def list_external_deployment_jobs(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExternalDeploymentJobListResponse:
    get_topology_for_user(db, user, topology_id)
    items = [_to_response(j) for j in job_svc.list_jobs_for_topology(db, topology_id)]
    return ExternalDeploymentJobListResponse(items=items)


@router.post(
    "/topologies/{topology_id}/external-deployment-jobs",
    response_model=ExternalDeploymentJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_external_deployment_job(
    topology_id: UUID,
    body: ExternalDeploymentJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExternalDeploymentJobResponse:
    require_topology_editor(db, user, topology_id)
    topo = get_topology_for_user(db, user, topology_id)
    if body.mode not in ENABLED_JOB_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mode '{body.mode}' is not enabled yet. "
                "Step 57A supports validate and plan only; apply/destroy coming later."
            ),
        )
    try:
        target_id = UUID(body.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid target_id") from exc
    target = target_svc.get_target(db, target_id)
    if target is None or target.project_id != topo.project_id:
        raise HTTPException(status_code=404, detail="Deployment target not found")
    try:
        job = job_svc.create_and_run_job(
            db,
            topology=topo,
            target=target,
            actor=user,
            mode=body.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(job)
    return _to_response(job)


@router.get(
    "/external-deployment-jobs/{job_id}",
    response_model=ExternalDeploymentJobResponse,
)
def get_external_deployment_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExternalDeploymentJobResponse:
    job = _get_job_for_user(db, user, job_id)
    return _to_response(job)


@router.get(
    "/external-deployment-jobs/{job_id}/logs",
    response_model=ExternalDeploymentJobLogsResponse,
)
def get_external_deployment_job_logs(
    job_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExternalDeploymentJobLogsResponse:
    job = _get_job_for_user(db, user, job_id)
    return ExternalDeploymentJobLogsResponse(
        job_id=str(job.id),
        status=job.status,
        logs=job.logs or "",
    )
