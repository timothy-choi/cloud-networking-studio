"""Deployment target CRUD (Step 57A)."""

from __future__ import annotations

import copy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_masking import scrub_sensitive_dict
from app.models.deployment_target import DeploymentTarget
from app.models.user import User
from app.services.audit_service import record_audit

TARGET_TYPES = frozenset({"remote_docker", "kubernetes", "terraform", "ansible"})
TARGET_STATUSES = frozenset({"active", "disabled"})


def list_targets(db: Session, project_id: UUID) -> list[DeploymentTarget]:
    return list(
        db.scalars(
            select(DeploymentTarget)
            .where(DeploymentTarget.project_id == project_id)
            .order_by(DeploymentTarget.name.asc())
        ).all()
    )


def get_target(db: Session, target_id: UUID) -> DeploymentTarget | None:
    return db.get(DeploymentTarget, target_id)


def create_target(
    db: Session,
    *,
    project_id: UUID,
    actor: User,
    name: str,
    target_type: str,
    config_json: dict | None,
    credentials_ref: str | None,
    status: str = "active",
) -> DeploymentTarget:
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Invalid target_type: {target_type}")
    if status not in TARGET_STATUSES:
        status = "active"
    target = DeploymentTarget(
        project_id=project_id,
        name=name.strip(),
        target_type=target_type,
        config_json=scrub_sensitive_dict(copy.deepcopy(config_json or {})),
        credentials_ref=(credentials_ref or "").strip() or None,
        status=status,
        created_by_user_id=actor.id,
    )
    db.add(target)
    db.flush()
    record_audit(
        db,
        action="deployment_target.created",
        resource_type="deployment_target",
        resource_id=target.id,
        project_id=project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "target_type": target.target_type,
                "status": target.status,
                "credentials_ref": target.credentials_ref,
            }
        ),
    )
    return target


def update_target(
    db: Session,
    *,
    target: DeploymentTarget,
    actor: User,
    name: str | None = None,
    config_json: dict | None = None,
    credentials_ref: str | None = None,
    status: str | None = None,
    *,
    update_name: bool = False,
    update_config_json: bool = False,
    update_credentials_ref: bool = False,
    update_status: bool = False,
) -> DeploymentTarget:
    changes: dict[str, object] = {}

    if update_name:
        if name is None:
            raise ValueError("name cannot be empty")
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        target.name = cleaned
        changes["name"] = cleaned

    if update_config_json:
        target.config_json = scrub_sensitive_dict(copy.deepcopy(config_json or {}))
        changes["config_json"] = "updated"

    if update_credentials_ref:
        target.credentials_ref = (credentials_ref or "").strip() or None
        changes["credentials_ref"] = target.credentials_ref

    if update_status:
        if status is None or status not in TARGET_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        target.status = status
        changes["status"] = status

    if not changes:
        raise ValueError("No fields to update")

    db.flush()
    record_audit(
        db,
        action="deployment_target.updated",
        resource_type="deployment_target",
        resource_id=target.id,
        project_id=target.project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "target_type": target.target_type,
                "changes": changes,
            }
        ),
    )
    return target
