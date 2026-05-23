"""Record platform audit events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models.audit_log import AuditLog

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "authorization",
        "jwt",
        "api_key",
    }
)


def _scrub_metadata(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    out: dict[str, Any] = {}
    for k, v in data.items():
        lk = k.lower()
        if lk in _SENSITIVE_KEYS or "token" in lk or "secret" in lk:
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = _scrub_metadata(v) or {}
        else:
            out[k] = v
    return out


def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None = None,
    project_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    commit: bool = False,
) -> AuditLog:
    rid = request_id or get_request_id()
    rid_str = str(rid) if rid else None
    res_id = str(resource_id) if resource_id is not None else None
    row = AuditLog(
        project_id=project_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=res_id,
        status=status,
        metadata_json=_scrub_metadata(metadata),
        request_id=rid_str,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def list_project_audit_logs(
    db: Session,
    project_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
    )
    return list(db.execute(stmt).scalars().all())


def list_deployment_audit_logs(
    db: Session,
    deployment_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    dep_id = str(deployment_id)
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.resource_type == "deployment",
            AuditLog.resource_id == dep_id,
        )
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
    )
    return list(db.execute(stmt).scalars().all())
