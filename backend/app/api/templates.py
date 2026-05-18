"""Runtime topology templates — save from topology, list, clone, delete (Step 43)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.topologies import _counts_for_topology
from app.db.session import get_db
from app.models.user import User
from app.schemas.template import (
    RuntimeTemplateDetailResponse,
    RuntimeTemplateResponse,
    TemplateCloneRequest,
    TemplateFromTopologyCreate,
)
from app.schemas.topology import TopologyResponse
from app.services.access_control import get_project_role_for_topology
from app.services import template_service as tmpl_svc

router = APIRouter(tags=["templates"])


@router.post(
    "/templates/from-topology/{topology_id}",
    response_model=RuntimeTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save current topology as a reusable template",
)
def post_template_from_topology(
    topology_id: UUID,
    body: TemplateFromTopologyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeTemplateDetailResponse:
    try:
        out = tmpl_svc.create_template_from_topology(db, user, topology_id, body)
    except ValueError as exc:
        msg = str(exc).lower()
        code = status.HTTP_404_NOT_FOUND if "not found" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    db.commit()
    return out


@router.get(
    "/templates",
    response_model=list[RuntimeTemplateResponse],
    summary="List templates you can use (project + private + catalog)",
)
def list_templates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Case-insensitive name contains"),
) -> list[RuntimeTemplateResponse]:
    rows = tmpl_svc.list_templates(db, user, project_id=project_id, category=category, q=q)
    db.commit()
    return rows


@router.get(
    "/templates/{template_id}",
    response_model=RuntimeTemplateDetailResponse,
    summary="Template detail including topology snapshot JSON",
)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeTemplateDetailResponse:
    try:
        out = tmpl_svc.get_template_detail(db, user, template_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    db.commit()
    return out


@router.post(
    "/templates/{template_id}/clone",
    response_model=TopologyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft topology from a template",
)
def post_template_clone(
    template_id: UUID,
    body: TemplateCloneRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyResponse:
    try:
        topo = tmpl_svc.clone_template_to_topology(db, user, template_id, body)
    except ValueError as exc:
        msg = str(exc).lower()
        code = status.HTTP_404_NOT_FOUND if "not found" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    db.commit()
    db.refresh(topo)
    n, l = _counts_for_topology(db, topo.id)
    role = get_project_role_for_topology(db, user, topo.id)
    return TopologyResponse.model_validate(topo).model_copy(
        update={"node_count": n, "link_count": l, "my_role": role}
    )


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a template (creator or project owner; not built-ins)",
)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        tmpl_svc.delete_template(db, user, template_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
