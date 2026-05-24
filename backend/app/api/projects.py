"""Project CRUD and team membership (RBAC)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.topology import Topology
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.project_member import (
    ProjectMemberResponse,
    ProjectMemberRoleUpdate,
)
from app.services.access_control import get_project_for_member, require_project_owner
from app.schemas.quota import ProjectQuotaResponse, QuotaLimits, QuotaRemaining, QuotaUsage
from app.services.project_member_service import (
    member_response,
    remove_member,
    transfer_ownership,
    update_member_role,
)
from app.services.quota_service import build_project_quota_usage

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_response(proj: Project, role: str) -> ProjectResponse:
    return ProjectResponse.model_validate(proj).model_copy(update={"my_role": role})


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create project")
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    proj = Project(
        owner_user_id=user.id,
        name=body.name.strip(),
        description=body.description.strip() if body.description else None,
    )
    db.add(proj)
    db.flush()
    db.add(ProjectMembership(project_id=proj.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(proj)
    return _project_response(proj, "owner")


@router.get("", response_model=list[ProjectResponse], summary="List my projects")
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    stmt = (
        select(Project, ProjectMembership.role)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .where(ProjectMembership.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return [_project_response(p, r) for p, r in rows]


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse], summary="List project members")
def list_project_members(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectMemberResponse]:
    get_project_for_member(db, user, project_id)
    stmt = (
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project_id)
        .order_by(ProjectMembership.created_at.asc())
    )
    out: list[ProjectMemberResponse] = []
    for m, u in db.execute(stmt).all():
        out.append(
            ProjectMemberResponse(
                id=m.id,
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=m.role,
                created_at=m.created_at,
            )
        )
    return out


@router.patch(
    "/{project_id}/members/{member_id}",
    response_model=ProjectMemberResponse,
    summary="Update member role",
)
def patch_project_member(
    project_id: UUID,
    member_id: UUID,
    body: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMemberResponse:
    project = require_project_owner(db, user, project_id)
    m = db.get(ProjectMembership, member_id)
    if m is None or m.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        out = update_member_role(
            db,
            project=project,
            membership=m,
            new_role=body.role,
            actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return out


@router.post(
    "/{project_id}/members/{member_id}/transfer-ownership",
    response_model=ProjectMemberResponse,
    summary="Transfer project ownership",
)
def post_transfer_ownership(
    project_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMemberResponse:
    project = require_project_owner(db, user, project_id)
    from_m = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user.id,
        )
    )
    to_m = db.get(ProjectMembership, member_id)
    if from_m is None or to_m is None or to_m.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        out = transfer_ownership(
            db,
            project=project,
            from_membership=from_m,
            to_membership=to_m,
            actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return out


@router.delete(
    "/{project_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove project member",
)
def delete_project_member(
    project_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    project = require_project_owner(db, user, project_id)
    m = db.get(ProjectMembership, member_id)
    if m is None or m.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        remove_member(db, project=project, membership=m, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project")
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    proj, role = get_project_for_member(db, user, project_id)
    return _project_response(proj, role)


@router.get(
    "/{project_id}/quotas",
    response_model=ProjectQuotaResponse,
    summary="Project quota limits and current usage",
)
def get_project_quotas(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectQuotaResponse:
    get_project_for_member(db, user, project_id)
    raw = build_project_quota_usage(db, project_id, user.id)
    return ProjectQuotaResponse(
        project_id=project_id,
        limits=QuotaLimits.model_validate(raw["limits"]),
        usage=QuotaUsage.model_validate(raw["usage"]),
        remaining=QuotaRemaining.model_validate(raw["remaining"]),
    )


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update project")
def patch_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    proj = require_project_owner(db, user, project_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        proj.name = str(data["name"]).strip()
    if "description" in data:
        d = data["description"]
        if d is None:
            proj.description = None
        else:
            s = str(d).strip()
            proj.description = s if s else None
    db.commit()
    db.refresh(proj)
    _, role = get_project_for_member(db, user, project_id)
    return _project_response(proj, role)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete project")
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    proj = require_project_owner(db, user, project_id)
    n = db.scalar(select(func.count()).select_from(Topology).where(Topology.project_id == project_id)) or 0
    if int(n) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project still has topologies; delete or move them first.",
        )
    db.delete(proj)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
