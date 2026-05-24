"""Project invitation routes (Step 54B)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.project_invitation import (
    InvitationActionResponse,
    ProjectInvitationCreate,
    ProjectInvitationCreatedResponse,
    ProjectInvitationResponse,
)
from app.services.access_control import require_project_owner
from app.services.project_invitation_service import (
    accept_invitation,
    create_project_invitation,
    decline_invitation,
    list_project_invitations,
    revoke_project_invitation,
)
from app.services.rate_limit_service import check_rate_limit

router = APIRouter(tags=["invitations"])


@router.post(
    "/projects/{project_id}/invitations",
    response_model=ProjectInvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite user by email",
)
def post_project_invitation(
    project_id: UUID,
    body: ProjectInvitationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectInvitationCreatedResponse:
    check_rate_limit(
        key=f"invite:user:{user.id}",
        limit=settings.rate_limit_invite_per_user,
        action="invite",
    )
    project = require_project_owner(db, user, project_id)
    try:
        return create_project_invitation(
            db,
            project=project,
            inviter=user,
            email=str(body.email),
            role=body.role,
        )
    except ValueError as exc:
        msg = str(exc)
        code = status.HTTP_400_BAD_REQUEST
        if "already exists" in msg.lower() or "already a member" in msg.lower():
            code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=msg) from exc
    finally:
        db.commit()


@router.get(
    "/projects/{project_id}/invitations",
    response_model=list[ProjectInvitationResponse],
    summary="List project invitations",
)
def get_project_invitations(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectInvitationResponse]:
    from app.services.access_control import get_project_for_member

    get_project_for_member(db, user, project_id)
    rows = list_project_invitations(db, project_id)
    db.commit()
    return rows


@router.post(
    "/projects/{project_id}/invitations/{invitation_id}/revoke",
    response_model=ProjectInvitationResponse,
    summary="Revoke pending invitation",
)
def post_revoke_invitation(
    project_id: UUID,
    invitation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectInvitationResponse:
    require_project_owner(db, user, project_id)
    try:
        out = revoke_project_invitation(
            db,
            project_id=project_id,
            invitation_id=invitation_id,
            actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    return out


@router.post(
    "/invitations/{token}/accept",
    response_model=InvitationActionResponse,
    summary="Accept project invitation",
)
def post_accept_invitation(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InvitationActionResponse:
    try:
        row, _ = accept_invitation(db, raw_token=token, user=user)
    except ValueError as exc:
        msg = str(exc)
        code = status.HTTP_400_BAD_REQUEST
        if "already a member" in msg.lower():
            code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=msg) from exc
    db.commit()
    return InvitationActionResponse(
        status="accepted",
        message="Invitation accepted. You now have access to the project.",
        project_id=row.project_id,
    )


@router.post(
    "/invitations/{token}/decline",
    response_model=InvitationActionResponse,
    summary="Decline project invitation",
)
def post_decline_invitation(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InvitationActionResponse:
    try:
        row = decline_invitation(db, raw_token=token, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return InvitationActionResponse(
        status="declined",
        message="Invitation declined.",
        project_id=row.project_id,
    )
