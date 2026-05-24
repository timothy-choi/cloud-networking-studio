"""Project member management with audit and notifications (Step 54B)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.schemas.project_member import ProjectMemberResponse
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user

_log = logging.getLogger("cns.members")


def count_owners(db: Session, project_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.role == "owner",
            )
        )
        or 0
    )


def member_response(db: Session, m: ProjectMembership) -> ProjectMemberResponse:
    u = db.get(User, m.user_id)
    assert u is not None
    return ProjectMemberResponse(
        id=m.id,
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=m.role,
        created_at=m.created_at,
    )


def update_member_role(
    db: Session,
    *,
    project: Project,
    membership: ProjectMembership,
    new_role: str,
    actor: User,
) -> ProjectMemberResponse:
    old_role = membership.role
    if membership.role == "owner" and new_role != "owner" and count_owners(db, project.id) <= 1:
        raise ValueError("Cannot demote the only project owner.")
    membership.role = new_role
    if new_role == "owner":
        project.owner_user_id = membership.user_id
    db.flush()
    record_audit(
        db,
        action="project.member.role_changed",
        resource_type="project_membership",
        resource_id=membership.id,
        project_id=project.id,
        actor_user_id=actor.id,
        status="success",
        metadata={"user_id": str(membership.user_id), "from_role": old_role, "to_role": new_role},
    )
    target = db.get(User, membership.user_id)
    if target is not None:
        try:
            notify_user(
                db,
                target.id,
                type="project.member.role_changed",
                title=f"Role updated in {project.name}",
                message=f"Your role changed from {old_role} to {new_role}.",
                severity="info",
                project_id=project.id,
                metadata={"url": "/dashboard"},
            )
        except Exception:
            _log.exception("role change notification failed")
    return member_response(db, membership)


def remove_member(
    db: Session,
    *,
    project: Project,
    membership: ProjectMembership,
    actor: User,
) -> None:
    if membership.role == "owner" and count_owners(db, project.id) <= 1:
        raise ValueError("Cannot remove the only project owner.")
    mid = membership.id
    uid = membership.user_id
    role = membership.role
    db.delete(membership)
    db.flush()
    record_audit(
        db,
        action="project.member.removed",
        resource_type="project_membership",
        resource_id=mid,
        project_id=project.id,
        actor_user_id=actor.id,
        status="success",
        metadata={"user_id": str(uid), "role": role},
    )
    try:
        notify_user(
            db,
            uid,
            type="project.member.removed",
            title=f"Removed from {project.name}",
            message="You no longer have access to this project.",
            severity="warning",
            project_id=project.id,
        )
    except Exception:
        _log.exception("remove member notification failed")


def transfer_ownership(
    db: Session,
    *,
    project: Project,
    from_membership: ProjectMembership,
    to_membership: ProjectMembership,
    actor: User,
) -> ProjectMemberResponse:
    if from_membership.role != "owner":
        raise ValueError("Only owners can transfer ownership.")
    if to_membership.project_id != project.id:
        raise ValueError("Target must be a project member.")
    if to_membership.user_id == from_membership.user_id:
        raise ValueError("Cannot transfer ownership to yourself.")

    to_membership.role = "owner"
    from_membership.role = "member"
    project.owner_user_id = to_membership.user_id
    db.flush()

    record_audit(
        db,
        action="project.ownership.transferred",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
        actor_user_id=actor.id,
        status="success",
        metadata={
            "from_user_id": str(from_membership.user_id),
            "to_user_id": str(to_membership.user_id),
        },
    )

    new_owner = db.get(User, to_membership.user_id)
    prev_owner = db.get(User, from_membership.user_id)
    try:
        if new_owner is not None:
            notify_user(
                db,
                new_owner.id,
                type="project.ownership.transferred",
                title=f"You are now owner of {project.name}",
                message=f"{prev_owner.display_name if prev_owner else 'Previous owner'} transferred ownership to you.",
                severity="success",
                project_id=project.id,
                metadata={"url": "/dashboard"},
            )
        if prev_owner is not None:
            notify_user(
                db,
                prev_owner.id,
                type="project.ownership.transferred",
                title=f"Ownership transferred: {project.name}",
                message=f"You transferred ownership to {new_owner.display_name if new_owner else 'new owner'}.",
                severity="info",
                project_id=project.id,
                metadata={"url": "/dashboard"},
            )
    except Exception:
        _log.exception("ownership transfer notification failed")

    return member_response(db, to_membership)
