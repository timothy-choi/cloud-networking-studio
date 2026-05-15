"""Project / topology ownership checks for API routes (404 for cross-tenant access)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.failure_injection import FailureInjection
from app.models.project import Project
from app.models.topology import Topology, TopologyNode
from app.models.traffic_test import TrafficTest
from app.models.user import User


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def get_owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    proj = db.get(Project, project_id)
    if proj is None or proj.owner_user_id != user.id:
        raise _not_found()
    return proj


def get_topology_for_user(db: Session, user: User, topology_id: uuid.UUID) -> Topology:
    stmt = (
        select(Topology)
        .join(Project, Topology.project_id == Project.id)
        .where(Topology.id == topology_id, Project.owner_user_id == user.id)
    )
    topo = db.execute(stmt).scalar_one_or_none()
    if topo is None:
        raise _not_found()
    return topo


def get_deployment_for_user(db: Session, user: User, deployment_id: uuid.UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .join(Topology, Deployment.topology_id == Topology.id)
        .join(Project, Topology.project_id == Project.id)
        .where(Deployment.id == deployment_id, Project.owner_user_id == user.id)
    )
    dep = db.execute(stmt).scalar_one_or_none()
    if dep is None:
        raise _not_found()
    return dep


def get_node_for_user(db: Session, user: User, node_id: uuid.UUID) -> TopologyNode:
    stmt = (
        select(TopologyNode)
        .join(Topology, TopologyNode.topology_id == Topology.id)
        .join(Project, Topology.project_id == Project.id)
        .where(TopologyNode.id == node_id, Project.owner_user_id == user.id)
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
        select(Project).where(Project.owner_user_id == user.id).order_by(Project.created_at.asc()).limit(1)
    )
