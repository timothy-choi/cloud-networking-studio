"""Deployment target CRUD (Step 57A)."""

from __future__ import annotations

import copy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_masking import scrub_sensitive_dict
from app.models.deployment_target import DeploymentTarget
from app.models.external_deployment import ExternalDeployment
from app.models.user import User
from app.services.audit_service import record_audit

TARGET_TYPES = frozenset({"remote_docker", "kubernetes", "terraform", "ansible"})
RUNTIME_TARGET_TYPES = frozenset({"remote_docker", "kubernetes"})
LEGACY_INFRA_TARGET_TYPES = frozenset({"terraform", "ansible"})
TARGET_STATUSES = frozenset({"active", "disabled"})
DOCUMENTATION_TEST_HOSTS = frozenset({"203.0.113.10", "192.0.2.1", "198.51.100.1"})


def is_documentation_test_host(host: str | None) -> bool:
    if not host:
        return False
    return host.strip() in DOCUMENTATION_TEST_HOSTS


def mock_target_config_overrides(*, is_mock: bool, host: str) -> dict[str, object]:
    disabled = is_mock or is_documentation_test_host(host)
    if not disabled:
        return {}
    reason = (
        "Mock/simulated target — real workload apply is disabled for workflow testing only."
        if is_mock
        else f"Documentation/test IP ({host}) — real workload apply is disabled."
    )
    return {
        "is_mock": is_mock,
        "mock_label": "Mock target — for workflow testing only" if is_mock else None,
        "workload_apply_disabled": True,
        "workload_apply_disabled_reason": reason,
    }


def runtime_target_snapshot(target: DeploymentTarget) -> dict:
    host = (target.config_json or {}).get("host")
    return {
        "target_id": str(target.id),
        "name": target.name,
        "host": host,
        "target_type": target.target_type,
        "is_mock": bool((target.config_json or {}).get("is_mock")),
        "infrastructure_deployment_id": (
            str(target.infrastructure_deployment_id) if target.infrastructure_deployment_id else None
        ),
    }


def list_targets_for_infrastructure_deployment(
    db: Session,
    infrastructure_deployment_id: UUID,
) -> list[DeploymentTarget]:
    return list(
        db.scalars(
            select(DeploymentTarget)
            .where(DeploymentTarget.infrastructure_deployment_id == infrastructure_deployment_id)
            .order_by(DeploymentTarget.created_at.asc())
        ).all()
    )


def count_active_external_deployments(db: Session, target_id: UUID) -> int:
    return len(
        db.scalars(
            select(ExternalDeployment).where(
                ExternalDeployment.target_id == target_id,
                ExternalDeployment.status == "active",
            )
        ).all()
    )


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
    infrastructure_deployment_id: UUID | None = None,
) -> DeploymentTarget:
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Invalid target_type: {target_type}")
    if target_type in LEGACY_INFRA_TARGET_TYPES:
        raise ValueError(
            f"target_type '{target_type}' is not a runtime target. "
            "Use Infrastructure Deployments for Terraform/Ansible provisioning."
        )
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
        infrastructure_deployment_id=infrastructure_deployment_id,
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


def delete_target(
    db: Session,
    *,
    target: DeploymentTarget,
    actor: User,
    force: bool = False,
) -> None:
    active_count = count_active_external_deployments(db, target.id)
    if active_count > 0 and not force:
        raise ValueError(
            "Cannot delete target with active workload deployments. "
            "Destroy them first or retry with force=true."
        )
    infra_deployment_id = target.infrastructure_deployment_id
    target_id = target.id
    project_id = target.project_id
    target_type = target.target_type
    db.delete(target)
    db.flush()
    record_audit(
        db,
        action="deployment_target.deleted",
        resource_type="deployment_target",
        resource_id=target_id,
        project_id=project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "target_type": target_type,
                "infrastructure_deployment_id": (
                    str(infra_deployment_id) if infra_deployment_id else None
                ),
                "force": force,
                "active_external_deployments": active_count,
            }
        ),
    )
