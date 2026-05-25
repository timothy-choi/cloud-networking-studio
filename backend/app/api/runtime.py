"""Runtime inspection, logs/stats, and reconciliation routes."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deployment import DeploymentEvent, DeploymentEventLevel
from app.models.user import User
from app.runtime.go_runner_client import effective_runtime_executor
from app.runtime.runner_operation_history import list_recent_runner_operations
from app.runtime.runner_runtime_error import (
    clear_runtime_error_if_operation_succeeded,
    get_runtime_error,
    set_runtime_error,
)
from app.schemas.runner_status import (
    LastRuntimeErrorDetail,
    RecentRunnerOperationsResponse,
    RunnerOperationRecordResponse,
    RunnerStatusDetailResponse,
)
from app.services.access_control import (
    get_node_for_user,
    get_topology_for_user,
    require_deployment_editor,
)
from app.services import runtime_state_service as runtime_svc
from app.schemas.runtime import (
    ReconciliationResponse,
    RuntimeLogsResponse,
    RuntimeStatsResponse,
    RuntimeTopologyResponse,
    StoppedContainerRef,
)

router = APIRouter(tags=["runtime"])


def _active_runtime_error() -> LastRuntimeErrorDetail | None:
    payload = get_runtime_error(include_historical=False)
    if payload is None:
        return None
    return LastRuntimeErrorDetail.model_validate(payload)


def _runner_detail_from_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "runner_status": data.get("runner_status") or data.get("status"),
        "status": data.get("status"),
        "runtime_provider": data.get("runtime_provider"),
        "docker_reachable": data.get("docker_reachable"),
        "kubernetes_reachable": data.get("kubernetes_reachable"),
        "current_context": data.get("current_context") or "",
        "version": data.get("version"),
        "git_sha": data.get("git_sha"),
        "build_time": data.get("build_time"),
        "supported_operations": data.get("supported_operations") or [],
        "message": data.get("message"),
    }


def _fetch_runner_status_detail() -> tuple[dict[str, Any] | None, str | None, int | None]:
    """Returns (runner_payload, error_message, status_code)."""
    from app.runtime.go_runner_client import GoRunnerClient

    try:
        data = GoRunnerClient.from_settings().get_runner_status()
    except httpx.HTTPStatusError as exc:
        msg = str(exc.response.text or exc.response.reason_phrase or exc)[:500]
        return None, msg, exc.response.status_code
    except (httpx.HTTPError, ValueError) as exc:
        return None, str(exc)[:500], None
    if not isinstance(data, dict):
        return None, "Go runner returned invalid JSON for /status", None
    return data, None, None


def _runner_status_response(*, checked_at: datetime | None = None) -> RunnerStatusDetailResponse:
    from app.core.config import settings

    checked = checked_at or datetime.now(UTC)
    executor = effective_runtime_executor()
    if executor != "go":
        return RunnerStatusDetailResponse(
            runner_reachable=False,
            runtime_executor=executor,
            runner_status="not_configured",
            status="not_configured",
            message="Go runner is not configured (RUNTIME_EXECUTOR=python)",
            checked_at=checked,
        )

    data, err, status_code = _fetch_runner_status_detail()
    if data is None:
        msg = err or "Go runner unavailable"
        active_err = _active_runtime_error()
        if active_err is None:
            set_runtime_error(
                operation="runner_status",
                message=msg,
                status_code=status_code,
            )
            active_err = _active_runtime_error()
        return RunnerStatusDetailResponse(
            runner_reachable=False,
            runtime_executor=executor,
            runner_status="unreachable",
            status="degraded",
            message=msg,
            last_runtime_error=active_err,
            checked_at=checked,
        )

    detail = _runner_detail_from_payload(data)
    return RunnerStatusDetailResponse(
        runner_reachable=True,
        runtime_executor=executor,
        checked_at=checked,
        last_runtime_error=_active_runtime_error(),
        **detail,
    )


def _python_executor_runtime_status() -> dict[str, Any]:
    """Control-plane view when Docker work runs in-process (docker-py)."""
    out: dict[str, Any] = {
        "status": "ok",
        "runtime_provider": "python",
        "runner_reachable": False,
        "docker_reachable": False,
        "kubernetes_reachable": False,
        "current_context": "",
        "message": "",
        "last_runtime_error": None,
    }
    active_err = _active_runtime_error()
    if active_err is not None:
        out["last_runtime_error"] = active_err.model_dump(mode="json")
    fake = os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes")
    if fake:
        out["message"] = "CNS_USE_FAKE_DOCKER: Docker engine not probed"
        return out
    try:
        import docker as docker_mod

        docker_mod.from_env().ping()
        out["docker_reachable"] = True
        clear_runtime_error_if_operation_succeeded("docker_probe")
    except Exception as exc:  # noqa: BLE001 — best-effort probe
        out["status"] = "degraded"
        out["docker_reachable"] = False
        err = str(exc)
        out["message"] = err
        set_runtime_error(operation="docker_probe", message=err)
        active_err = _active_runtime_error()
        if active_err is not None:
            out["last_runtime_error"] = active_err.model_dump(mode="json")
    return out


@router.get(
    "/runtime/status",
    summary="Control plane runtime executor status",
    response_description="Executor mode, runner reachability, and provider probes.",
)
def get_runtime_executor_status() -> dict[str, Any]:
    """
    Public probe (no DB, no auth) — same routing pattern as ``GET /health`` via ``/api/runtime/status``.

    * ``RUNTIME_EXECUTOR=python`` — local Docker ping when available.
    * ``RUNTIME_EXECUTOR=go`` — merges JSON from ``GO_RUNNER_URL/runtime/status``; if the runner is
      unreachable, returns HTTP 200 with ``status: degraded`` and ``runner_reachable: false``.
    """
    from app.core.config import settings

    executor = effective_runtime_executor()
    base: dict[str, Any] = {
        "backend_status": "ok",
        "runtime_executor": executor,
        "environment": settings.environment,
    }
    if effective_runtime_executor() == "go":
        from app.runtime.go_runner_client import GoRunnerClient

        checked_at = datetime.now(UTC)
        try:
            data = GoRunnerClient.from_settings().get_runtime_status()
        except (httpx.HTTPError, ValueError):
            runner_block = _runner_status_response(checked_at=checked_at)
            active_err = _active_runtime_error()
            return {
                **base,
                "status": "degraded",
                "runner_reachable": False,
                "runtime_provider": "unknown",
                "docker_reachable": False,
                "kubernetes_reachable": False,
                "current_context": "",
                "message": "Go runner unavailable",
                "last_runtime_error": active_err.model_dump(mode="json") if active_err else None,
                "runner": runner_block.model_dump(mode="json"),
                "checked_at": checked_at.isoformat(),
            }
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Go runner returned invalid JSON for /runtime/status",
            ) from None
        merged: dict[str, Any] = {**base, **data, "runner_reachable": True}
        merged["runtime_executor"] = executor
        if str(merged.get("status", "")).lower() != "ok":
            set_runtime_error(
                operation="runtime_status",
                message=str(merged.get("message") or merged.get("status") or "degraded"),
            )
        active_err = _active_runtime_error()
        merged["last_runtime_error"] = active_err.model_dump(mode="json") if active_err else None
        runner_detail = _runner_detail_from_payload(data)
        runner_detail["last_runtime_error"] = active_err.model_dump(mode="json") if active_err else None
        merged["runner"] = runner_detail
        merged["checked_at"] = checked_at.isoformat()
        return merged

    body = {**base, **_python_executor_runtime_status()}
    body["checked_at"] = datetime.now(UTC).isoformat()
    return body


@router.post(
    "/runtime/runner-recheck",
    summary="Re-probe Go runner and refresh runtime error state",
)
def recheck_runner_status() -> dict[str, Any]:
    """Force a fresh runner/runtime status probe (clears stale probe errors on success)."""
    return get_runtime_executor_status()


@router.get(
    "/runtime/runner-status",
    response_model=RunnerStatusDetailResponse,
    summary="Go runner observability status",
)
def get_runner_status() -> RunnerStatusDetailResponse:
    """Probe the Go runner process (when RUNTIME_EXECUTOR=go)."""
    return _runner_status_response()


@router.get(
    "/runtime/operations/recent",
    response_model=RecentRunnerOperationsResponse,
    summary="Recent backend → Go runner operations",
)
def get_recent_runner_operations(
    limit: int = Query(default=20, ge=1, le=50),
) -> RecentRunnerOperationsResponse:
    rows = list_recent_runner_operations(limit=limit)
    ops = [RunnerOperationRecordResponse.model_validate(row) for row in rows]
    return RecentRunnerOperationsResponse(operations=ops, count=len(ops))


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
    except Exception as exc:
        from app.core.errors import build_error_body

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=build_error_body(
                code="INTERNAL_ERROR",
                message="Failed to load topology runtime",
                status=500,
                details={"topology_id": str(topology_id), "reason": str(exc)[:500]},
            ),
        ) from exc


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
