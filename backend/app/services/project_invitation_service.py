"""Project invitation lifecycle (Step 54B)."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_api_token_secret, verify_api_token_secret
from app.models.project import Project
from app.models.project_invitation import ProjectInvitation
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.schemas.project_invitation import (
    ProjectInvitationCreatedResponse,
    ProjectInvitationResponse,
)
from app.services.audit_service import record_audit
from app.services.email_service import send_email
from app.services.notification_service import notify_project_owners, notify_user

_log = logging.getLogger("cns.invitations")

PENDING = "pending"
VALID_STATUSES = frozenset({"pending", "accepted", "declined", "expired", "revoked"})


def norm_email(email: str) -> str:
    return email.strip().lower()


def invitation_accept_url(raw_token: str) -> str:
    base = (settings.frontend_app_url or "https://app.cloudnetstudio.com").rstrip("/")
    from urllib.parse import quote

    return f"{base}/invitations/accept?token={quote(raw_token, safe='')}"


def _expire_stale_pending(db: Session, project_id: UUID | None = None) -> None:
    now = datetime.now(UTC)
    stmt = select(ProjectInvitation).where(
        ProjectInvitation.status == PENDING,
        ProjectInvitation.expires_at < now,
    )
    if project_id is not None:
        stmt = stmt.where(ProjectInvitation.project_id == project_id)
    for row in db.scalars(stmt).all():
        row.status = "expired"
        row.updated_at = now


def lookup_invitation_by_token(db: Session, raw_token: str) -> ProjectInvitation | None:
    token = (raw_token or "").strip()
    if token.count(".") != 1:
        return None
    left, secret = token.split(".", 1)
    if not left or not secret:
        return None
    try:
        iid = UUID(left)
    except ValueError:
        return None
    row = db.get(ProjectInvitation, iid)
    if row is None or not verify_api_token_secret(secret, row.token_hash):
        return None
    return row


def _to_response(row: ProjectInvitation) -> ProjectInvitationResponse:
    return ProjectInvitationResponse(
        id=row.id,
        project_id=row.project_id,
        email=row.email,
        role=row.role,
        status=row.status,
        invited_by_user_id=row.invited_by_user_id,
        accepted_by_user_id=row.accepted_by_user_id,
        expires_at=row.expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_project_invitations(db: Session, project_id: UUID) -> list[ProjectInvitationResponse]:
    _expire_stale_pending(db, project_id)
    db.flush()
    rows = list(
        db.scalars(
            select(ProjectInvitation)
            .where(ProjectInvitation.project_id == project_id)
            .order_by(ProjectInvitation.created_at.desc())
        ).all()
    )
    return [_to_response(r) for r in rows]


def create_project_invitation(
    db: Session,
    *,
    project: Project,
    inviter: User,
    email: str,
    role: str,
) -> ProjectInvitationCreatedResponse:
    from app.services import email_templates as tpl

    em = norm_email(email)
    if em == norm_email(inviter.email):
        raise ValueError("You cannot invite yourself.")

    existing_member = db.scalar(
        select(ProjectMembership.user_id)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project.id, User.email == em)
    )
    if existing_member is not None:
        raise ValueError("User is already a member of this project.")

    _expire_stale_pending(db, project.id)
    pending = db.scalar(
        select(ProjectInvitation.id).where(
            ProjectInvitation.project_id == project.id,
            ProjectInvitation.email == em,
            ProjectInvitation.status == PENDING,
        )
    )
    if pending is not None:
        raise ValueError("A pending invitation already exists for this email.")

    secret = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.invitation_expire_days)
    row = ProjectInvitation(
        project_id=project.id,
        email=em,
        role=role,
        token_hash=hash_api_token_secret(secret),
        status=PENDING,
        invited_by_user_id=inviter.id,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    raw_token = f"{row.id}.{secret}"
    accept_url = invitation_accept_url(raw_token)

    record_audit(
        db,
        action="project.invite.sent",
        resource_type="project_invitation",
        resource_id=row.id,
        project_id=project.id,
        actor_user_id=inviter.id,
        status="success",
        metadata={"email": em, "role": role},
    )

    inviter_name = inviter.display_name or inviter.email
    subj, text, html = tpl.project_invitation(
        project_name=project.name,
        inviter=inviter_name,
        role=role,
        accept_url=accept_url,
        expires_at=expires_at,
    )
    try:
        send_email(settings, to_email=em, subject=subj, body_text=text, body_html=html)
    except Exception:
        _log.exception("invite email failed for %s", em)

    invitee = db.scalar(select(User).where(User.email == em))
    if invitee is not None:
        try:
            notify_user(
                db,
                invitee.id,
                type="project.invitation",
                title=f"Invitation to {project.name}",
                message=f"{inviter_name} invited you to join as {role}.",
                severity="info",
                project_id=project.id,
                metadata={"url": "/invitations/accept", "invitation_id": str(row.id)},
            )
        except Exception:
            _log.exception("invite notification failed for user %s", invitee.id)

    db.flush()
    base = _to_response(row)
    return ProjectInvitationCreatedResponse(**base.model_dump(), accept_token=raw_token)


def revoke_project_invitation(
    db: Session,
    *,
    project_id: UUID,
    invitation_id: UUID,
    actor: User,
) -> ProjectInvitationResponse:
    row = db.get(ProjectInvitation, invitation_id)
    if row is None or row.project_id != project_id:
        raise ValueError("not found")
    if row.status != PENDING:
        raise ValueError("Only pending invitations can be revoked.")
    row.status = "revoked"
    row.updated_at = datetime.now(UTC)
    record_audit(
        db,
        action="project.invite.revoked",
        resource_type="project_invitation",
        resource_id=row.id,
        project_id=project_id,
        actor_user_id=actor.id,
        status="success",
        metadata={"email": row.email},
    )
    return _to_response(row)


def accept_invitation(
    db: Session,
    *,
    raw_token: str,
    user: User,
) -> tuple[ProjectInvitation, ProjectMembership]:
    row = lookup_invitation_by_token(db, raw_token)
    if row is None:
        raise ValueError("Invalid or expired invitation.")
    _expire_stale_pending(db, row.project_id)
    db.refresh(row)
    if row.status != PENDING:
        raise ValueError("This invitation is no longer available.")
    if row.expires_at < datetime.now(UTC):
        row.status = "expired"
        row.updated_at = datetime.now(UTC)
        raise ValueError("This invitation has expired.")
    if norm_email(user.email) != row.email:
        raise ValueError("Sign in with the invited email address to accept.")

    dup = db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == row.project_id,
            ProjectMembership.user_id == user.id,
        )
    )
    if dup is not None:
        row.status = "accepted"
        row.accepted_by_user_id = user.id
        row.updated_at = datetime.now(UTC)
        raise ValueError("You are already a member of this project.")

    membership = ProjectMembership(
        project_id=row.project_id,
        user_id=user.id,
        role=row.role,
    )
    db.add(membership)
    row.status = "accepted"
    row.accepted_by_user_id = user.id
    row.updated_at = datetime.now(UTC)
    db.flush()

    project = db.get(Project, row.project_id)
    project_name = project.name if project else "project"

    record_audit(
        db,
        action="project.invite.accepted",
        resource_type="project_invitation",
        resource_id=row.id,
        project_id=row.project_id,
        actor_user_id=user.id,
        status="success",
        metadata={"email": row.email, "role": row.role},
    )

    try:
        notify_project_owners(
            db,
            row.project_id,
            type="project.invite.accepted",
            title=f"Invitation accepted: {project_name}",
            message=f"{user.display_name or user.email} joined as {row.role}.",
            severity="success",
            metadata={"project_id": str(row.project_id)},
        )
        notify_user(
            db,
            user.id,
            type="project.invite.accepted",
            title=f"Welcome to {project_name}",
            message=f"You joined as {row.role}.",
            severity="success",
            project_id=row.project_id,
            metadata={"url": "/dashboard"},
        )
    except Exception:
        _log.exception("accept notification failed")

    return row, membership


def decline_invitation(
    db: Session,
    *,
    raw_token: str,
    user: User | None,
) -> ProjectInvitation:
    row = lookup_invitation_by_token(db, raw_token)
    if row is None:
        raise ValueError("Invalid or expired invitation.")
    _expire_stale_pending(db, row.project_id)
    db.refresh(row)
    if row.status != PENDING:
        raise ValueError("This invitation is no longer available.")
    if user is not None and norm_email(user.email) != row.email:
        raise ValueError("Sign in with the invited email address to decline.")

    row.status = "declined"
    row.updated_at = datetime.now(UTC)
    if user is not None:
        row.accepted_by_user_id = user.id

    project = db.get(Project, row.project_id)
    project_name = project.name if project else "project"

    record_audit(
        db,
        action="project.invite.declined",
        resource_type="project_invitation",
        resource_id=row.id,
        project_id=row.project_id,
        actor_user_id=user.id if user else None,
        status="success",
        metadata={"email": row.email},
    )

    try:
        notify_project_owners(
            db,
            row.project_id,
            type="project.invite.declined",
            title=f"Invitation declined: {project_name}",
            message=f"{row.email} declined the invitation.",
            severity="info",
        )
    except Exception:
        _log.exception("decline notification failed")

    return row
