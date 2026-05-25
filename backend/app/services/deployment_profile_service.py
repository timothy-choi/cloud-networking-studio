"""Deployment profile CRUD and defaults (Step 56)."""

from __future__ import annotations

import copy
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.secret_masking import scrub_sensitive_dict
from app.models.deployment_profile import DeploymentProfile
from app.models.topology import Topology
from app.models.user import User
from app.services.audit_service import record_audit

PROFILE_TYPES = frozenset({"dev", "staging", "prod_like", "custom"})


def list_profiles(db: Session, topology_id: UUID) -> list[DeploymentProfile]:
    return list(
        db.scalars(
            select(DeploymentProfile)
            .where(DeploymentProfile.topology_id == topology_id)
            .order_by(DeploymentProfile.is_default.desc(), DeploymentProfile.name.asc())
        ).all()
    )


def get_profile(db: Session, topology_id: UUID, profile_id: UUID) -> DeploymentProfile | None:
    return db.scalar(
        select(DeploymentProfile).where(
            DeploymentProfile.id == profile_id,
            DeploymentProfile.topology_id == topology_id,
        )
    )


def create_profile(
    db: Session,
    *,
    topology: Topology,
    actor: User,
    name: str,
    description: str | None,
    profile_type: str,
    config_json: dict | None,
    is_default: bool = False,
) -> DeploymentProfile:
    if profile_type not in PROFILE_TYPES:
        profile_type = "custom"
    if is_default:
        _clear_default(db, topology.id)
    profile = DeploymentProfile(
        topology_id=topology.id,
        name=name.strip(),
        description=description,
        profile_type=profile_type,
        config_json=copy.deepcopy(config_json) if config_json else {},
        is_default=is_default,
        created_by_user_id=actor.id,
    )
    db.add(profile)
    db.flush()
    record_audit(
        db,
        action="topology.profile.created",
        resource_type="deployment_profile",
        resource_id=profile.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status="success",
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology.id),
                "profile_type": profile.profile_type,
                "is_default": profile.is_default,
            }
        ),
    )
    return profile


def update_profile(
    db: Session,
    *,
    profile: DeploymentProfile,
    topology: Topology,
    actor: User,
    name: str | None = None,
    description: str | None = None,
    profile_type: str | None = None,
    config_json: dict | None = None,
) -> DeploymentProfile:
    if name is not None:
        profile.name = name.strip()
    if description is not None:
        profile.description = description
    if profile_type is not None and profile_type in PROFILE_TYPES:
        profile.profile_type = profile_type
    if config_json is not None:
        profile.config_json = copy.deepcopy(config_json)
    db.flush()
    record_audit(
        db,
        action="topology.profile.updated",
        resource_type="deployment_profile",
        resource_id=profile.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status="success",
        metadata=scrub_sensitive_dict({"topology_id": str(topology.id)}),
    )
    return profile


def delete_profile(
    db: Session,
    *,
    profile: DeploymentProfile,
    topology: Topology,
    actor: User,
) -> None:
    pid = profile.id
    db.delete(profile)
    db.flush()
    record_audit(
        db,
        action="topology.profile.deleted",
        resource_type="deployment_profile",
        resource_id=pid,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status="success",
        metadata=scrub_sensitive_dict({"topology_id": str(topology.id)}),
    )


def _clear_default(db: Session, topology_id: UUID) -> None:
    db.execute(
        update(DeploymentProfile)
        .where(DeploymentProfile.topology_id == topology_id)
        .values(is_default=False)
    )


def set_default_profile(
    db: Session,
    *,
    profile: DeploymentProfile,
    topology: Topology,
    actor: User,
) -> DeploymentProfile:
    _clear_default(db, topology.id)
    profile.is_default = True
    db.flush()
    record_audit(
        db,
        action="topology.profile.default_changed",
        resource_type="deployment_profile",
        resource_id=profile.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status="success",
        metadata=scrub_sensitive_dict({"topology_id": str(topology.id)}),
    )
    return profile
