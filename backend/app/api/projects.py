"""Project CRUD — owner-scoped."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.topology import Topology
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.access_control import get_owned_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create project")
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    proj = Project(
        owner_user_id=user.id,
        name=body.name.strip(),
        description=body.description.strip() if body.description else None,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@router.get("", response_model=list[ProjectResponse], summary="List my projects")
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Project]:
    stmt = select(Project).where(Project.owner_user_id == user.id).order_by(Project.created_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project")
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    return get_owned_project(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update project")
def patch_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    proj = get_owned_project(db, user, project_id)
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
    return proj


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete project")
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    proj = get_owned_project(db, user, project_id)
    n = db.scalar(select(func.count()).select_from(Topology).where(Topology.project_id == project_id)) or 0
    if int(n) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project still has topologies; delete or move them first.",
        )
    db.delete(proj)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
