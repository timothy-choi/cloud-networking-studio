"""Credential profile API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.credential_profile import (
    CredentialProfileCreate,
    CredentialProfileListResponse,
    CredentialProfileResponse,
    CredentialProfileUpdate,
    CredentialProfileValidateResponse,
)
from app.services.access_control import get_project_for_member, require_project_editor
from app.services import credential_profile_service as profile_svc

router = APIRouter(tags=["credential-profiles"])


def _to_response(row) -> CredentialProfileResponse:
    return CredentialProfileResponse(
        id=str(row.id),
        project_id=str(row.project_id),
        owner_id=str(row.owner_id),
        name=row.name,
        provider=row.provider,
        credential_type=row.credential_type,
        metadata_json=row.metadata_json or {},
        validation_status=row.validation_status,
        validation_message=row.validation_message,
        last_validated_at=row.last_validated_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        credentials_ref=profile_svc.credentials_ref_for_profile(row.id),
    )


@router.get(
    "/projects/{project_id}/credential-profiles",
    response_model=CredentialProfileListResponse,
)
def list_credential_profiles(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialProfileListResponse:
    get_project_for_member(db, user, project_id)
    items = [_to_response(row) for row in profile_svc.list_profiles(db, project_id)]
    return CredentialProfileListResponse(items=items)


@router.post(
    "/projects/{project_id}/credential-profiles",
    response_model=CredentialProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_credential_profile(
    project_id: UUID,
    body: CredentialProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialProfileResponse:
    require_project_editor(db, user, project_id)
    try:
        profile = profile_svc.create_profile(
            db,
            project_id=project_id,
            actor=user,
            name=body.name,
            provider=body.provider,
            credential_type=body.credential_type,
            secret=body.secret,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.get(
    "/credential-profiles/{profile_id}",
    response_model=CredentialProfileResponse,
)
def get_credential_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialProfileResponse:
    profile = profile_svc.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    get_project_for_member(db, user, profile.project_id)
    return _to_response(profile)


@router.patch(
    "/credential-profiles/{profile_id}",
    response_model=CredentialProfileResponse,
)
def update_credential_profile(
    profile_id: UUID,
    body: CredentialProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialProfileResponse:
    profile = profile_svc.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_project_editor(db, user, profile.project_id)
    try:
        profile = profile_svc.update_profile(
            db,
            profile=profile,
            actor=user,
            name=body.name,
            secret=body.secret,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.delete(
    "/credential-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_credential_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    profile = profile_svc.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_project_editor(db, user, profile.project_id)
    profile_svc.delete_profile(db, profile=profile, actor=user)
    db.commit()


@router.post(
    "/credential-profiles/{profile_id}/validate",
    response_model=CredentialProfileValidateResponse,
)
def validate_credential_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialProfileValidateResponse:
    profile = profile_svc.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_project_editor(db, user, profile.project_id)
    profile = profile_svc.validate_profile(db, profile=profile, actor=user)
    db.commit()
    db.refresh(profile)
    return CredentialProfileValidateResponse(
        id=str(profile.id),
        validation_status=profile.validation_status,
        validation_message=profile.validation_message,
        last_validated_at=profile.last_validated_at,
    )
