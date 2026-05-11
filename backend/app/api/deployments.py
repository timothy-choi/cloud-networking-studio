"""Deployment orchestration routes — persistence + runtime provider execution."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.schemas.deployment import DeploymentEventResponse, DeploymentResponse
from app.services.deployment_planner import build_deployment_plan

router = APIRouter(tags=["deployments"])


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


def _load_deployment_full(db: Session, deployment_id: UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()


@router.post(
    "/topologies/{topology_id}/deploy",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deploy topology",
    response_description="New deployment with nested audit events from the runtime provider.",
)
def deploy_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> Deployment:
    """Run deployment against the topology's runtime target (real Docker when target is docker)."""
    topo = _topology_or_404(db, topology_id)
    provider = runtime_provider_for_topology(topo.runtime_target)

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

    try:
        rows = provider.deploy(plan)
    except Exception as exc:
        deployment.status = DeploymentStatus.FAILED
        deployment.finished_at = datetime.utcnow()
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level=DeploymentEventLevel.ERROR,
                message=f"Deployment failed: {exc}",
            )
        )
        db.commit()
        return _load_deployment_full(db, deployment.id)

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level=level,
                message=msg,
            )
        )

    deployment.status = DeploymentStatus.SUCCEEDED
    deployment.finished_at = datetime.utcnow()
    db.commit()

    return _load_deployment_full(db, deployment.id)


@router.post(
    "/deployments/{deployment_id}/destroy",
    response_model=DeploymentResponse,
    summary="Destroy deployment",
    response_description="Deployment marked stopped after provider teardown; related events appended.",
)
def destroy_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
) -> Deployment:
    """Remove Docker resources labeled for this topology and mark deployment stopped."""
    dep = _deployment_or_404(db, deployment_id)
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )

    provider = runtime_provider_for_topology(dep.runtime_target)
    rows = provider.destroy(topo.id, dep.id)

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=level,
                message=msg,
            )
        )

    dep.status = DeploymentStatus.STOPPED
    dep.finished_at = datetime.utcnow()
    db.commit()

    return _load_deployment_full(db, deployment_id)


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentResponse,
    summary="Get deployment",
)
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
    summary="List deployment events",
    response_description="Append-only audit timeline for provisioning, inspection, and remediation.",
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
