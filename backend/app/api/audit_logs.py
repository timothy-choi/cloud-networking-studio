"""Audit log read endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogListResponse, AuditLogRead
from app.services.access_control import get_deployment_for_user, get_project_for_member
from app.services.audit_service import list_deployment_audit_logs, list_project_audit_logs

router = APIRouter(tags=["audit-logs"])


@router.get(
    "/projects/{project_id}/audit-logs",
    response_model=AuditLogListResponse,
    summary="List project audit logs",
)
def get_project_audit_logs(
    project_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    get_project_for_member(db, user, project_id)
    items = list_project_audit_logs(db, project_id, limit=limit, offset=offset)
    total = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.project_id == project_id)
    ).scalar_one()
    return AuditLogListResponse(items=[AuditLogRead.model_validate(i) for i in items], total=total)


@router.get(
    "/deployments/{deployment_id}/audit-logs",
    response_model=AuditLogListResponse,
    summary="List deployment-scoped audit logs",
)
def get_deployment_audit_logs(
    deployment_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    get_deployment_for_user(db, user, deployment_id)
    items = list_deployment_audit_logs(db, deployment_id, limit=limit, offset=offset)
    total = db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.resource_type == "deployment",
            AuditLog.resource_id == str(deployment_id),
        )
    ).scalar_one()
    return AuditLogListResponse(items=[AuditLogRead.model_validate(i) for i in items], total=total)
