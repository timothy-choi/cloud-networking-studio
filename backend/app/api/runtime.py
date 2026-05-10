"""Runtime inspection, logs/stats, and reconciliation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.deployment import DeploymentEvent, DeploymentEventLevel
from app.services import runtime_state_service as runtime_svc
from app.schemas.runtime import (
    ReconciliationResponse,
    RuntimeDeploymentResponse,
    RuntimeLogsResponse,
    RuntimeStatsResponse,
    RuntimeTopologyResponse,
    StoppedContainerRef,
)

router = APIRouter(tags=["runtime"])


def _topology_http(session, topology_id: UUID):
    try:
        return runtime_svc.build_topology_runtime(
            session,
            topology_id,
            emit_inspection_event=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )


def _deployment_http(session, deployment_id: UUID):
    try:
        return runtime_svc.build_deployment_runtime(
            session,
            deployment_id,
            emit_inspection_event=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )


@router.get(
    "/topologies/{topology_id}/runtime",
    response_model=RuntimeTopologyResponse,
)
def get_topology_runtime(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> RuntimeTopologyResponse:
    body = _topology_http(db, topology_id)
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime",
    response_model=RuntimeDeploymentResponse,
)
def get_deployment_runtime(
    deployment_id: UUID,
    db: Session = Depends(get_db),
) -> RuntimeDeploymentResponse:
    body = _deployment_http(db, deployment_id)
    db.commit()
    return body


@router.get(
    "/nodes/{node_id}/logs",
    response_model=RuntimeLogsResponse,
)
def get_node_logs(
    node_id: UUID,
    tail: int = Query(default=100, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> RuntimeLogsResponse:
    try:
        body = runtime_svc.build_node_logs(db, node_id, tail)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    if body is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runtime container not found for this node",
        )
    runtime_svc.record_logs_requested_event(db, body.topology_id, node_id, tail)
    db.commit()
    return body


@router.get(
    "/nodes/{node_id}/stats",
    response_model=RuntimeStatsResponse,
)
def get_node_stats(
    node_id: UUID,
    db: Session = Depends(get_db),
) -> RuntimeStatsResponse:
    try:
        body = runtime_svc.build_node_stats(db, node_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    if body is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Runtime container not found or stats unavailable",
        )
    runtime_svc.record_stats_requested_event(db, body.topology_id, node_id)
    db.commit()
    return body


@router.post(
    "/deployments/{deployment_id}/reconcile",
    response_model=ReconciliationResponse,
)
def reconcile_deployment_route(
    deployment_id: UUID,
    db: Session = Depends(get_db),
) -> ReconciliationResponse:
    try:
        dep, result = runtime_svc.reconcile_deployment(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment or topology not found",
        )

    tid = dep.topology_id
    db.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message="Runtime reconciliation started",
        )
    )
    if result.missing_network:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message="Missing resource detected: managed topology network not found",
            )
        )
    for nid in result.missing_node_ids:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=f"Missing resource detected: container for node_id={nid}",
            )
        )
    for cid, name in result.stopped_containers:
        sid = cid[:12] if cid else "?"
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=DeploymentEventLevel.WARNING,
                message=f"Stopped container detected: {name} ({sid})",
            )
        )
    summary_msg = "Runtime reconciliation completed"
    if result.summary_lines:
        summary_msg += ": " + " | ".join(result.summary_lines)
    db.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message=summary_msg,
        )
    )
    db.commit()

    return ReconciliationResponse(
        deployment_id=dep.id,
        topology_id=tid,
        missing_network=result.missing_network,
        missing_node_ids=list(result.missing_node_ids),
        stopped_containers=[
            StoppedContainerRef(container_id=cid, name=nm)
            for cid, nm in result.stopped_containers
        ],
        summary_lines=list(result.summary_lines),
    )
