"""Deployment profile API routes (Step 56)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.deployment_profile import (
    DeploymentProfileCreate,
    DeploymentProfileListResponse,
    DeploymentProfileResponse,
    DeploymentProfileUpdate,
)
from app.services.access_control import (
    get_topology_for_user,
    require_project_owner,
    require_topology_editor,
)
from app.services import deployment_profile_service as profile_svc

router = APIRouter(prefix="/topologies/{topology_id}/profiles", tags=["deployment-profiles"])


def _to_response(p) -> DeploymentProfileResponse:
    return DeploymentProfileResponse.model_validate(p)


@router.get("", response_model=DeploymentProfileListResponse)
def list_deployment_profiles(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentProfileListResponse:
    get_topology_for_user(db, user, topology_id)
    items = [_to_response(p) for p in profile_svc.list_profiles(db, topology_id)]
    return DeploymentProfileListResponse(items=items)


@router.post("", response_model=DeploymentProfileResponse, status_code=status.HTTP_201_CREATED)
def create_deployment_profile(
    topology_id: UUID,
    body: DeploymentProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentProfileResponse:
    require_topology_editor(db, user, topology_id)
    topo = get_topology_for_user(db, user, topology_id)
    profile = profile_svc.create_profile(
        db,
        topology=topo,
        actor=user,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        config_json=body.config_json,
        is_default=body.is_default,
    )
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.get("/{profile_id}", response_model=DeploymentProfileResponse)
def get_deployment_profile(
    topology_id: UUID,
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentProfileResponse:
    get_topology_for_user(db, user, topology_id)
    profile = profile_svc.get_profile(db, topology_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_response(profile)


@router.patch("/{profile_id}", response_model=DeploymentProfileResponse)
def update_deployment_profile(
    topology_id: UUID,
    profile_id: UUID,
    body: DeploymentProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentProfileResponse:
    require_topology_editor(db, user, topology_id)
    topo = get_topology_for_user(db, user, topology_id)
    profile = profile_svc.get_profile(db, topology_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    profile = profile_svc.update_profile(
        db,
        profile=profile,
        topology=topo,
        actor=user,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        config_json=body.config_json,
    )
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment_profile(
    topology_id: UUID,
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    topo = get_topology_for_user(db, user, topology_id)
    require_project_owner(db, user, topo.project_id)
    profile = profile_svc.get_profile(db, topology_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    profile_svc.delete_profile(db, profile=profile, topology=topo, actor=user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/set-default", response_model=DeploymentProfileResponse)
def set_default_deployment_profile(
    topology_id: UUID,
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentProfileResponse:
    topo = get_topology_for_user(db, user, topology_id)
    require_project_owner(db, user, topo.project_id)
    profile = profile_svc.get_profile(db, topology_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    profile = profile_svc.set_default_profile(db, profile=profile, topology=topo, actor=user)
    db.commit()
    db.refresh(profile)
    return _to_response(profile)
