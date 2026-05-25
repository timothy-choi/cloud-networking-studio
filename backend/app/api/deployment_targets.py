"""Deployment target API routes (Step 57A)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.deployment_target import (
    DeploymentTargetCreate,
    DeploymentTargetListResponse,
    DeploymentTargetResponse,
    DeploymentTargetUpdate,
)
from app.services.access_control import get_project_for_member, require_project_editor
from app.services import deployment_target_service as target_svc

router = APIRouter(tags=["deployment-targets"])


def _to_response(target) -> DeploymentTargetResponse:
    return DeploymentTargetResponse(
        id=str(target.id),
        project_id=str(target.project_id),
        name=target.name,
        target_type=target.target_type,
        config_json=target.config_json or {},
        credentials_ref=target.credentials_ref,
        status=target.status,
        created_by_user_id=str(target.created_by_user_id) if target.created_by_user_id else None,
        created_at=target.created_at,
    )


@router.get(
    "/projects/{project_id}/deployment-targets",
    response_model=DeploymentTargetListResponse,
)
def list_deployment_targets(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentTargetListResponse:
    get_project_for_member(db, user, project_id)
    items = [_to_response(t) for t in target_svc.list_targets(db, project_id)]
    return DeploymentTargetListResponse(items=items)


@router.post(
    "/projects/{project_id}/deployment-targets",
    response_model=DeploymentTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment_target(
    project_id: UUID,
    body: DeploymentTargetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentTargetResponse:
    require_project_editor(db, user, project_id)
    try:
        target = target_svc.create_target(
            db,
            project_id=project_id,
            actor=user,
            name=body.name,
            target_type=body.target_type,
            config_json=body.config_json,
            credentials_ref=body.credentials_ref,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(target)
    return _to_response(target)


@router.patch(
    "/deployment-targets/{target_id}",
    response_model=DeploymentTargetResponse,
)
def update_deployment_target(
    target_id: UUID,
    body: DeploymentTargetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentTargetResponse:
    target = target_svc.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_project_editor(db, user, target.project_id)
    fields = body.model_fields_set
    try:
        target = target_svc.update_target(
            db,
            target=target,
            actor=user,
            name=body.name,
            config_json=body.config_json,
            credentials_ref=body.credentials_ref,
            status=body.status,
            update_name="name" in fields,
            update_config_json="config_json" in fields,
            update_credentials_ref="credentials_ref" in fields,
            update_status="status" in fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(target)
    return _to_response(target)


@router.get(
    "/deployment-targets/{target_id}",
    response_model=DeploymentTargetResponse,
)
def get_deployment_target(
    target_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentTargetResponse:
    target = target_svc.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    get_project_for_member(db, user, target.project_id)
    return _to_response(target)
