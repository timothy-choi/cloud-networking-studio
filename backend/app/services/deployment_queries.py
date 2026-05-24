"""Shared deployment lookups for APIs and runtime aggregation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentStatus


def latest_deployment_for_topology(session: Session, topology_id: UUID) -> Deployment | None:
    stmt = (
        select(Deployment)
        .where(Deployment.topology_id == topology_id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def deployment_status_blocks_new_deploy(status: DeploymentStatus) -> bool:
    """Statuses that mean workloads may still exist or deploy is in flight."""
    return status in (
        DeploymentStatus.PENDING,
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.STOPPING,
        DeploymentStatus.SUCCEEDED,
    )


def list_active_deployments_for_topology(session: Session, topology_id: UUID) -> list[Deployment]:
    """Deployments that may still have runtime resources or block new deploys."""
    stmt = (
        select(Deployment)
        .where(
            Deployment.topology_id == topology_id,
            Deployment.status.in_(
                (
                    DeploymentStatus.PENDING,
                    DeploymentStatus.DEPLOYING,
                    DeploymentStatus.STOPPING,
                    DeploymentStatus.SUCCEEDED,
                )
            ),
        )
        .order_by(Deployment.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def active_deployment_blocking_new_deploy(
    session: Session, topology_id: UUID
) -> Deployment | None:
    """Latest deployment for the topology if it blocks starting another deploy."""
    dep = latest_deployment_for_topology(session, topology_id)
    if dep is None:
        return None
    if deployment_status_blocks_new_deploy(dep.status):
        return dep
    return None
