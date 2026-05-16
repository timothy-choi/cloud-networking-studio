"""Failure injection — controlled node disruption for resilience testing."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.failure_injection import FailureInjectionFailureType
from app.models.user import User
from app.schemas.failure_injection import (
    FailureInjectionRequest,
    FailureInjectionResponse,
)
from app.services import failure_injection_service as fi_svc
from app.services.access_control import (
    get_failure_injection_for_user,
    get_topology_for_user,
    require_topology_editor,
)

router = APIRouter(tags=["failure-injections"])


@router.post(
    "/topologies/{topology_id}/failures/stop-node",
    response_model=FailureInjectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inject stop container failure",
)
def inject_stop_node(
    topology_id: UUID,
    body: FailureInjectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FailureInjectionResponse:
    require_topology_editor(db, user, topology_id)
    try:
        fi = fi_svc.run_failure_injection(
            db,
            topology_id,
            body.target_node_id,
            FailureInjectionFailureType.STOP_CONTAINER,
            body.description,
        )
    except LookupError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    db.commit()
    db.refresh(fi)
    return fi


@router.post(
    "/topologies/{topology_id}/failures/restart-node",
    response_model=FailureInjectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inject restart container failure",
)
def inject_restart_node(
    topology_id: UUID,
    body: FailureInjectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FailureInjectionResponse:
    require_topology_editor(db, user, topology_id)
    try:
        fi = fi_svc.run_failure_injection(
            db,
            topology_id,
            body.target_node_id,
            FailureInjectionFailureType.RESTART_CONTAINER,
            body.description,
        )
    except LookupError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    db.commit()
    db.refresh(fi)
    return fi


@router.post(
    "/topologies/{topology_id}/failures/kill-node",
    response_model=FailureInjectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inject kill container failure",
)
def inject_kill_node(
    topology_id: UUID,
    body: FailureInjectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FailureInjectionResponse:
    require_topology_editor(db, user, topology_id)
    try:
        fi = fi_svc.run_failure_injection(
            db,
            topology_id,
            body.target_node_id,
            FailureInjectionFailureType.KILL_CONTAINER,
            body.description,
        )
    except LookupError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    db.commit()
    db.refresh(fi)
    return fi


@router.get(
    "/failures/{failure_id}",
    response_model=FailureInjectionResponse,
    summary="Get failure injection",
)
def get_failure_injection(
    failure_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FailureInjectionResponse:
    return get_failure_injection_for_user(db, user, failure_id)


@router.get(
    "/topologies/{topology_id}/failures",
    response_model=list[FailureInjectionResponse],
    summary="List topology failure injections",
)
def list_topology_failures(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FailureInjectionResponse]:
    get_topology_for_user(db, user, topology_id)
    return fi_svc.list_failure_injections_for_topology(db, topology_id)
