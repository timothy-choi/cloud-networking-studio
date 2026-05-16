"""Project / topology access checks: membership + RBAC (404 for unknown / non-member)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.failure_injection import FailureInjection
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.topology import Topology, TopologyNode
from app.models.traffic_test import TrafficTest
from app.models.user import User

ROLE_LEVEL = {"viewer": 0, "member": 1, "owner": 2}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def forbidden_editor() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This action requires editor access (owner or member).",
    )


def forbidden_owner() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This action requires project owner access.",
    )


def get_project_membership_role(db: Session, user: User, project_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(ProjectMembership.role).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user.id,
        )
    )


def get_project_for_member(db: Session, user: User, project_id: uuid.UUID) -> tuple[Project, str]:
    proj = db.get(Project, project_id)
    if proj is None:
        raise _not_found()
    role = get_project_membership_role(db, user, project_id)
    if role is None:
        raise _not_found()
    return proj, role


def require_project_owner(db: Session, user: User, project_id: uuid.UUID) -> Project:
    proj, role = get_project_for_member(db, user, project_id)
    if role != "owner":
        raise forbidden_owner()
    return proj


def require_project_editor(db: Session, user: User, project_id: uuid.UUID) -> tuple[Project, str]:
    proj, role = get_project_for_member(db, user, project_id)
    if ROLE_LEVEL[role] < ROLE_LEVEL["member"]:
        raise forbidden_editor()
    return proj, role


def get_project_role_for_topology(db: Session, user: User, topology_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(ProjectMembership.role)
        .join(Topology, Topology.project_id == ProjectMembership.project_id)
        .where(Topology.id == topology_id, ProjectMembership.user_id == user.id)
    )


def get_topology_for_user(db: Session, user: User, topology_id: uuid.UUID) -> Topology:
    stmt = (
        select(Topology)
        .join(Project, Topology.project_id == Project.id)
        .join(
            ProjectMembership,
            (ProjectMembership.project_id == Project.id)
            & (ProjectMembership.user_id == user.id),
        )
        .where(Topology.id == topology_id)
    )
    topo = db.execute(stmt).scalar_one_or_none()
    if topo is None:
        raise _not_found()
    return topo


def require_topology_editor(db: Session, user: User, topology_id: uuid.UUID) -> Topology:
    topo = get_topology_for_user(db, user, topology_id)
    role = get_project_role_for_topology(db, user, topology_id)
    if role is None or ROLE_LEVEL[role] < ROLE_LEVEL["member"]:
        raise forbidden_editor()
    return topo


def get_deployment_for_user(db: Session, user: User, deployment_id: uuid.UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .join(Topology, Deployment.topology_id == Topology.id)
        .join(Project, Topology.project_id == Project.id)
        .join(
            ProjectMembership,
            (ProjectMembership.project_id == Project.id)
            & (ProjectMembership.user_id == user.id),
        )
        .where(Deployment.id == deployment_id)
    )
    dep = db.execute(stmt).scalar_one_or_none()
    if dep is None:
        raise _not_found()
    return dep


def require_deployment_editor(db: Session, user: User, deployment_id: uuid.UUID) -> Deployment:
    dep = get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, dep.topology_id)
    return dep


def get_node_for_user(db: Session, user: User, node_id: uuid.UUID) -> TopologyNode:
    stmt = (
        select(TopologyNode)
        .join(Topology, TopologyNode.topology_id == Topology.id)
        .join(Project, Topology.project_id == Project.id)
        .join(
            ProjectMembership,
            (ProjectMembership.project_id == Project.id)
            & (ProjectMembership.user_id == user.id),
        )
        .where(TopologyNode.id == node_id)
    )
    node = db.execute(stmt).scalar_one_or_none()
    if node is None:
        raise _not_found()
    return node


def get_traffic_test_for_user(db: Session, user: User, traffic_test_id: uuid.UUID) -> TrafficTest:
    tt = db.get(TrafficTest, traffic_test_id)
    if tt is None:
        raise _not_found()
    get_topology_for_user(db, user, tt.topology_id)
    return tt


def get_failure_injection_for_user(db: Session, user: User, failure_id: uuid.UUID) -> FailureInjection:
    fi = db.get(FailureInjection, failure_id)
    if fi is None:
        raise _not_found()
    get_topology_for_user(db, user, fi.topology_id)
    return fi


def default_project_for_user(db: Session, user: User) -> Project | None:
    return db.scalar(
        select(Project)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .where(ProjectMembership.user_id == user.id)
        .order_by(Project.created_at.asc())
        .limit(1)
    )
