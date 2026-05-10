"""Deployment orchestration routes — persistence + simulated provider execution."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider
from app.providers.runtime_provider import RuntimeProvider
from app.schemas.deployment import DeploymentEventResponse, DeploymentResponse
from app.services.deployment_planner import build_deployment_plan

router = APIRouter(tags=["deployments"])


def _get_runtime_provider() -> RuntimeProvider:
    """FastAPI dependency hook for future DI (real Docker/K8s providers)."""
    return FakeDockerRuntimeProvider()


def _topology_or_404(db: Session, topology_id: UUID) -> Topology:
    stmt = (
        select(Topology)
        .where(Topology.id == topology_id)
        .options(
            selectinload(Topology.nodes),
            selectinload(Topology.links),
        )
    )
    topo = db.execute(stmt).scalar_one_or_none()
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    return topo


def _deployment_or_404(db: Session, deployment_id: UUID) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )
    return dep


@router.post(
    "/topologies/{topology_id}/deploy",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def deploy_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
    provider: RuntimeProvider = Depends(_get_runtime_provider),
) -> Deployment:
    """Simulate a deployment run and persist events (no real containers)."""
    topo = _topology_or_404(db, topology_id)

    deployment = Deployment(
        topology_id=topology_id,
        status=DeploymentStatus.PENDING,
        runtime_target=topo.runtime_target,
    )
    db.add(deployment)
    db.flush()

    deployment.started_at = datetime.utcnow()
    deployment.status = DeploymentStatus.PROVISIONING

    plan = build_deployment_plan(topo)
    messages = provider.deploy(plan)

    for msg in messages:
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level=DeploymentEventLevel.INFO,
                message=msg,
            )
        )

    deployment.status = DeploymentStatus.SUCCEEDED
    deployment.finished_at = datetime.utcnow()
    db.commit()

    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment.id)
        .options(selectinload(Deployment.events))
    )
    deployment = db.execute(stmt).scalar_one()
    return deployment


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
) -> Deployment:
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    dep = db.execute(stmt).scalar_one_or_none()
    if dep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )
    return dep


@router.get(
    "/deployments/{deployment_id}/events",
    response_model=list[DeploymentEventResponse],
)
def list_deployment_events(
    deployment_id: UUID,
    db: Session = Depends(get_db),
) -> list[DeploymentEvent]:
    _deployment_or_404(db, deployment_id)
    stmt = (
        select(DeploymentEvent)
        .where(DeploymentEvent.deployment_id == deployment_id)
        .order_by(DeploymentEvent.created_at.asc())
    )
    return list(db.scalars(stmt).all())
