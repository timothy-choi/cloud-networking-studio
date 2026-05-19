"""Safe exec persistence and runner delegation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.deployment_runtime_exec_result import DeploymentRuntimeExecResult
from app.models.topology import Topology
from app.runtime import go_runner_client as grc

_log = logging.getLogger(__name__)
from app.schemas.runtime_exec import (
    RuntimeExecResultListResponse,
    RuntimeExecResultResponse,
    RuntimeRestartResponse,
)
from app.services.runtime_operations_service import get_runtime_resource_row, workload_node_id
from app.services.safe_exec_allowlist import validate_command


def _use_go() -> bool:
    return grc.effective_runtime_executor().strip().lower() == "go"


def _runner() -> grc.GoRunnerClient:
    return grc.GoRunnerClient.from_settings()


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _row_to_response(row: DeploymentRuntimeExecResult) -> RuntimeExecResultResponse:
    return RuntimeExecResultResponse(
        id=row.id,
        deployment_id=row.deployment_id,
        service_id=row.runtime_resource_id,
        command=row.command,
        status=row.status,
        exit_code=row.exit_code,
        stdout=row.stdout or "",
        stderr=row.stderr or "",
        started_at=row.started_at,
        finished_at=row.finished_at,
        runtime_provider=row.runtime_provider,
        message=row.message,
    )


def run_safe_exec(
    db: Session,
    user_id: UUID,
    deployment_id: UUID,
    runtime_resource_id: UUID,
    command: str,
    timeout_seconds: int,
) -> RuntimeExecResultResponse:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    res = get_runtime_resource_row(db, deployment_id, runtime_resource_id)
    wid = workload_node_id(res)
    if wid is None:
        raise ValueError("runtime resource has no workload node id")

    prov = (dep.runtime_target or "docker").strip() or "docker"
    started = datetime.now(UTC)
    cmd_s = (command or "").strip()

    row = DeploymentRuntimeExecResult(
        deployment_id=deployment_id,
        runtime_resource_id=runtime_resource_id,
        command=cmd_s,
        status="rejected",
        stdout="",
        stderr="",
        runtime_provider=prov,
        started_at=started,
        created_by_user_id=user_id,
    )
    db.add(row)
    db.flush()

    argv, err_msg = validate_command(cmd_s)
    if err_msg:
        row.status = "rejected"
        row.message = err_msg
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return _row_to_response(row)

    if not grc.should_delegate_runtime_ops_to_go_runner():
        _log.info(
            "effective_runtime_executor=%s exec unsupported (control-plane fallback) deployment_id=%s service_id=%s",
            grc.effective_runtime_executor(),
            deployment_id,
            runtime_resource_id,
        )
        row.status = "unsupported"
        row.message = (
            "Remote exec requires RUNTIME_EXECUTOR=go so commands run inside the workload via the Go runner."
        )
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return _row_to_response(row)

    grc.log_runtime_op_delegation("exec", deployment_id, service_id=runtime_resource_id)
    body = {"command": cmd_s, "timeout_seconds": timeout_seconds}
    try:
        data = _runner().post_runtime_service_exec(
            deployment_id,
            dep.topology_id,
            str(wid),
            body,
            project_id=topo.project_id,
        )
    except httpx.HTTPStatusError as exc:
        row.status = "failed"
        row.message = f"runner HTTP {exc.response.status_code}"
        try:
            row.stderr = (exc.response.text or "")[:8000]
        except Exception:
            row.stderr = ""
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return _row_to_response(row)
    except httpx.HTTPError as exc:
        row.status = "failed"
        row.message = str(exc)
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return _row_to_response(row)

    row.status = str(data.get("status") or "failed")
    row.stdout = str(data.get("stdout") or "")
    row.stderr = str(data.get("stderr") or "")
    row.message = str(data.get("message") or "") or None
    ec = data.get("exit_code")
    if ec is not None:
        try:
            row.exit_code = int(ec)
        except (TypeError, ValueError):
            row.exit_code = None
    row.started_at = _parse_ts(data.get("started_at")) or row.started_at
    row.finished_at = _parse_ts(data.get("finished_at")) or datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _row_to_response(row)


def list_exec_results(db: Session, deployment_id: UUID, limit: int = 50) -> RuntimeExecResultListResponse:
    limit = max(1, min(limit, 100))
    rows = list(
        db.scalars(
            select(DeploymentRuntimeExecResult)
            .where(DeploymentRuntimeExecResult.deployment_id == deployment_id)
            .order_by(DeploymentRuntimeExecResult.created_at.desc())
            .limit(limit)
        ).all()
    )
    return RuntimeExecResultListResponse(
        deployment_id=deployment_id,
        items=[_row_to_response(r) for r in rows],
    )


def get_exec_result(db: Session, deployment_id: UUID, exec_result_id: UUID) -> RuntimeExecResultResponse:
    row = db.get(DeploymentRuntimeExecResult, exec_result_id)
    if row is None or row.deployment_id != deployment_id:
        raise ValueError("not found")
    return _row_to_response(row)


def run_restart(
    db: Session,
    deployment_id: UUID,
    runtime_resource_id: UUID,
) -> RuntimeRestartResponse:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    res = get_runtime_resource_row(db, deployment_id, runtime_resource_id)
    wid = workload_node_id(res)
    if wid is None:
        raise ValueError("runtime resource has no workload node id")
    prov = (dep.runtime_target or "docker").strip() or "docker"

    if not grc.should_delegate_runtime_ops_to_go_runner():
        _log.info(
            "effective_runtime_executor=%s restart unsupported (control-plane fallback) deployment_id=%s service_id=%s",
            grc.effective_runtime_executor(),
            deployment_id,
            runtime_resource_id,
        )
        return RuntimeRestartResponse(
            status="unsupported",
            message=(
                "Restart requires RUNTIME_EXECUTOR=go so the Go runner can restart the workload in the runtime."
            ),
            runtime_provider=prov,
        )

    grc.log_runtime_op_delegation("restart", deployment_id, service_id=runtime_resource_id)
    try:
        data = _runner().post_runtime_service_restart(
            deployment_id,
            dep.topology_id,
            str(wid),
            project_id=topo.project_id,
        )
    except httpx.HTTPStatusError as exc:
        msg = f"runner HTTP {exc.response.status_code}"
        try:
            tail = (exc.response.text or "")[:800]
            if tail.strip():
                msg = f"{msg}: {tail.strip()}"
        except Exception:
            pass
        return RuntimeRestartResponse(status="failed", message=msg, runtime_provider=prov)
    except httpx.HTTPError as exc:
        return RuntimeRestartResponse(status="failed", message=str(exc), runtime_provider=prov)

    return RuntimeRestartResponse(
        status=str(data.get("status") or "failed"),
        message=str(data.get("message") or ""),
        runtime_provider=str(data.get("runtime_provider") or prov),
    )
