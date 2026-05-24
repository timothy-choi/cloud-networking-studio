"""Notification creation and delivery helpers (Step 54A)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secret_masking import scrub_sensitive_dict
from app.models.notification import Notification
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.email_service import send_email

_log = logging.getLogger("cns.notifications")

VALID_STATUSES = frozenset({"unread", "read", "archived"})
VALID_SEVERITIES = frozenset({"info", "success", "warning", "error"})


def _scrub_meta(data: dict[str, Any] | None) -> dict[str, Any] | None:
    return scrub_sensitive_dict(data)


def create_notification(
    db: Session,
    *,
    user_id: UUID | None,
    project_id: UUID | None = None,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
    send_email: bool = False,
    email_to: str | None = None,
    email_subject: str | None = None,
    email_text: str | None = None,
    email_html: str | None = None,
    commit: bool = False,
) -> Notification:
    sev = severity if severity in VALID_SEVERITIES else "info"
    row = Notification(
        user_id=user_id,
        project_id=project_id,
        type=type.strip(),
        title=title.strip()[:256],
        message=message.strip()[:2048],
        status="unread",
        severity=sev,
        metadata_json=_scrub_meta(metadata),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        action="notification.created",
        resource_type="notification",
        resource_id=row.id,
        project_id=project_id,
        actor_user_id=user_id,
        status="success",
        metadata={"type": type, "severity": sev},
    )
    if send_email and email_to and email_subject and email_text:
        _try_send_email(
            db,
            to_email=email_to,
            subject=email_subject,
            body_text=email_text,
            body_html=email_html,
            user_id=user_id,
            project_id=project_id,
        )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def _try_send_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    user_id: UUID | None,
    project_id: UUID | None,
) -> None:
    try:
        ok = send_email(
            settings,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        record_audit(
            db,
            action="email.sent" if ok else "email.failed",
            resource_type="email",
            resource_id=None,
            project_id=project_id,
            actor_user_id=user_id,
            status="success" if ok else "failure",
            metadata={"to": to_email, "subject": subject},
        )
    except Exception:
        _log.exception("email send failed for %s", to_email)
        try:
            record_audit(
                db,
                action="email.failed",
                resource_type="email",
                project_id=project_id,
                actor_user_id=user_id,
                status="failure",
                metadata={"to": to_email},
            )
        except Exception:
            _log.exception("audit after email failure failed")


def notify_user(
    db: Session,
    user_id: UUID,
    *,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    project_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    send_email: bool = False,
    email_subject: str | None = None,
    email_text: str | None = None,
    email_html: str | None = None,
) -> Notification:
    email_to: str | None = None
    if send_email:
        user = db.get(User, user_id)
        email_to = user.email if user else None
    return create_notification(
        db,
        user_id=user_id,
        project_id=project_id,
        type=type,
        title=title,
        message=message,
        severity=severity,
        metadata=metadata,
        send_email=send_email,
        email_to=email_to,
        email_subject=email_subject,
        email_text=email_text,
        email_html=email_html,
    )


def _member_user_ids(db: Session, project_id: UUID, *, owners_only: bool = False) -> list[UUID]:
    stmt = select(ProjectMembership.user_id).where(ProjectMembership.project_id == project_id)
    if owners_only:
        stmt = stmt.where(ProjectMembership.role == "owner")
    return list(db.scalars(stmt).all())


def notify_project_members(
    db: Session,
    project_id: UUID,
    *,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
    send_email: bool = False,
    email_subject: str | None = None,
    email_text: str | None = None,
    email_html: str | None = None,
) -> list[Notification]:
    rows: list[Notification] = []
    for uid in _member_user_ids(db, project_id):
        rows.append(
            notify_user(
                db,
                uid,
                type=type,
                title=title,
                message=message,
                severity=severity,
                project_id=project_id,
                metadata=metadata,
                send_email=send_email,
                email_subject=email_subject,
                email_text=email_text,
                email_html=email_html,
            )
        )
    return rows


def notify_project_owners(
    db: Session,
    project_id: UUID,
    *,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
    send_email: bool = False,
    email_subject: str | None = None,
    email_text: str | None = None,
    email_html: str | None = None,
) -> list[Notification]:
    rows: list[Notification] = []
    for uid in _member_user_ids(db, project_id, owners_only=True):
        rows.append(
            notify_user(
                db,
                uid,
                type=type,
                title=title,
                message=message,
                severity=severity,
                project_id=project_id,
                metadata=metadata,
                send_email=send_email,
                email_subject=email_subject,
                email_text=email_text,
                email_html=email_html,
            )
        )
    return rows


def _visible_filter(user_id: UUID):
    """User-owned rows, or project-scoped rows where user is a member."""
    member_projects = select(ProjectMembership.project_id).where(
        ProjectMembership.user_id == user_id
    )
    return or_(
        Notification.user_id == user_id,
        (
            Notification.project_id.in_(member_projects)
            & Notification.user_id.is_(None)
        ),
    )


def list_notifications(
    db: Session,
    user_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> list[Notification]:
    stmt = select(Notification).where(_visible_filter(user_id))
    if not include_archived:
        stmt = stmt.where(Notification.status != "archived")
    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(min(limit, 200))
    return list(db.scalars(stmt).all())


def unread_count(db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(_visible_filter(user_id), Notification.status == "unread")
        )
        or 0
    )


def get_notification_for_user(db: Session, user_id: UUID, notification_id: UUID) -> Notification | None:
    return db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            _visible_filter(user_id),
        )
    )


def mark_read(db: Session, user_id: UUID, notification_id: UUID) -> Notification:
    row = get_notification_for_user(db, user_id, notification_id)
    if row is None:
        raise ValueError("not found")
    if row.status == "unread":
        row.status = "read"
        row.read_at = datetime.now(UTC)
    return row


def mark_all_read(db: Session, user_id: UUID) -> int:
    rows = list(
        db.scalars(
            select(Notification).where(_visible_filter(user_id), Notification.status == "unread")
        ).all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.status = "read"
        row.read_at = now
    return len(rows)


def archive_notification(db: Session, user_id: UUID, notification_id: UUID) -> Notification:
    row = get_notification_for_user(db, user_id, notification_id)
    if row is None:
        raise ValueError("not found")
    row.status = "archived"
    return row


def notify_deployment_outcome(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID | None,
    topology_id: UUID,
    deployment_id: UUID,
    topology_name: str,
    succeeded: bool,
    reason: str | None = None,
    send_email: bool = False,
) -> None:
    from app.services import email_templates as tpl

    meta = {
        "topology_id": str(topology_id),
        "deployment_id": str(deployment_id),
        "url": f"/topologies/{topology_id}",
    }
    try:
        if succeeded:
            subj, text, html = tpl.deployment_succeeded(
                topology_name=topology_name, deployment_id=str(deployment_id)
            )
            notify_user(
                db,
                user_id,
                type="deployment.succeeded",
                title=f"Deployment succeeded: {topology_name}",
                message=f"Deployment for {topology_name} completed successfully.",
                severity="success",
                project_id=project_id,
                metadata=meta,
                send_email=send_email,
                email_subject=subj,
                email_text=text,
                email_html=html,
            )
        else:
            subj, text, html = tpl.deployment_failed(
                topology_name=topology_name,
                deployment_id=str(deployment_id),
                reason=reason or "Unknown error",
            )
            notify_user(
                db,
                user_id,
                type="deployment.failed",
                title=f"Deployment failed: {topology_name}",
                message=reason or "Deployment failed.",
                severity="error",
                project_id=project_id,
                metadata=meta,
                send_email=send_email,
                email_subject=subj,
                email_text=text,
                email_html=html,
            )
    except Exception:
        _log.exception("notify_deployment_outcome failed")


def notify_quota_exceeded_event(
    db: Session,
    *,
    user_id: UUID | None,
    project_id: UUID | None,
    quota: str,
    message: str,
    send_email: bool = False,
) -> None:
    if user_id is None:
        return
    from app.services import email_templates as tpl

    subj, text, html = tpl.quota_exceeded(quota=quota, message=message)
    try:
        notify_user(
            db,
            user_id,
            type="quota.exceeded",
            title=f"Quota exceeded: {quota}",
            message=message,
            severity="warning",
            project_id=project_id,
            metadata={"quota": quota},
            send_email=send_email,
            email_subject=subj,
            email_text=text,
            email_html=html,
        )
    except Exception:
        _log.exception("notify_quota_exceeded failed")
