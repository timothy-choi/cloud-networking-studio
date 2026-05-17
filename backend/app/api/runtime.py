"""Runtime inspection, logs/stats, and reconciliation routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deployment import DeploymentEvent, DeploymentEventLevel
from app.models.user import User
from app.services import runtime_state_service as runtime_svc
from app.services.access_control import (
    get_node_for_user,
    get_topology_for_user,
    require_deployment_editor,
)
from app.runtime.go_runner_client import effective_runtime_executor
from app.schemas.runtime import (
    ReconciliationResponse,
    RuntimeLogsResponse,
    RuntimeStatsResponse,
    RuntimeTopologyResponse,
    StoppedContainerRef,
)

router = APIRouter(tags=["runtime"])


def _python_executor_runtime_status() -> dict[str, Any]:
    """Local control-plane view when Docker work runs in-process (docker-py)."""
    return {
        "status": "ok",
        "runtime_provider": "python",
    }


@router.get(
    "/runtime/status",
    summary="Control plane runtime executor status",
    response_description="Executor mode: python returns fixed JSON; go proxies the runner.",
)
def get_runtime_executor_status() -> dict[str, Any]:
    """
    Public probe (no DB, no auth) — same routing pattern as ``GET /health`` via ``/api/runtime/status``.

    * ``RUNTIME_EXECUTOR=python`` — ``{"status":"ok","runtime_provider":"python"}``.
    * ``RUNTIME_EXECUTOR=go`` — JSON from ``GO_RUNNER_URL/runtime/status`` (503 if unreachable).
    """
    if effective_runtime_executor() == "go":
        from app.runtime.go_runner_client import GoRunnerClient

        try:
            return GoRunnerClient.from_settings().get_runtime_status()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Go runner unavailable",
            ) from None
    return _python_executor_runtime_status()


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
        ) from None


@router.get(
    "/topologies/{topology_id}/runtime",
    response_model=RuntimeTopologyResponse,
    summary="Topology runtime snapshot",
)
def get_topology_runtime(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeTopologyResponse:
    get_topology_for_user(db, user, topology_id)
    body = _topology_http(db, topology_id)
    db.commit()
    return body


@router.get(
    "/nodes/{node_id}/logs",
    response_model=RuntimeLogsResponse,
    summary="Fetch container logs for node",
)
def get_node_logs(
    node_id: UUID,
    tail: int = Query(default=100, ge=1, le=10000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeLogsResponse:
    get_node_for_user(db, user, node_id)
    try:
        body = runtime_svc.build_node_logs(db, node_id, tail)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        ) from None
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
    summary="Container stats for node",
)
def get_node_stats(
    node_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeStatsResponse:
    get_node_for_user(db, user, node_id)
    try:
        body = runtime_svc.build_node_stats(db, node_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        ) from None
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
    summary="Reconcile deployment runtime",
    response_description="Structured drift findings versus Docker actuals; persists summary deployment events.",
)
def reconcile_deployment_route(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReconciliationResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        dep, result = runtime_svc.reconcile_deployment(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment or topology not found",
        ) from None

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
