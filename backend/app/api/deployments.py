"""Deployment orchestration routes — persistence + runtime provider execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
import httpx
from starlette.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel, DeploymentStatus
from app.models.topology import Topology
from app.models.user import User
from app.services.access_control import get_deployment_for_user, require_deployment_editor
from app.services import topology_deploy_execution as topology_deploy_execution
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.schemas.deploy import TopologyDeployRequest
from app.schemas.deployment import DeploymentEventResponse, DeploymentResponse
from app.schemas.runtime import (
    RuntimeDeploymentResponse,
    RuntimeDeploymentSectionResponse,
    RuntimeDeploymentServicesSectionResponse,
    RuntimeInstructionsOnlyResponse,
    RuntimeOperationsHealthResponse,
    RuntimeOperationsLogsResponse,
    RuntimeOperationsTrafficRequest,
    RuntimeOperationsTrafficResponse,
)
from app.schemas.runtime_exec import (
    RuntimeExecRequestBody,
    RuntimeExecResultListResponse,
    RuntimeExecResultResponse,
    RuntimeRestartResponse,
)
from app.schemas.integration_outputs import DeploymentIntegrationOutputsResponse, IntegrationOutputFileItem
from app.schemas.runtime_integration import (
    DeploymentIntegrationResponse,
    DeploymentRuntimeMappingResponse,
)
from app.schemas.runtime_terminal import TerminalSessionCreateResponse
from app.schemas.service_exposure import (
    ServiceExposureCreate,
    ServiceExposureListResponse,
    ServiceExposureResponse,
)
from app.services.deployment_service_exposure_service import DuplicateExposureError
from app.services import deployment_service_exposure_service as exposure_svc
from app.services import runtime_exec_service as runtime_exec_svc
from app.services import integration_outputs_service as integration_outputs_svc
from app.services import runtime_integration_service as integration_svc
from app.services import runtime_operations_service as runtime_ops
from app.services import runtime_state_service as runtime_svc
from app.services import runtime_terminal_service as terminal_svc
from app.models.deployment_runtime_resource import DeploymentRuntimeResource

router = APIRouter(tags=["deployments"])


def _load_deployment_full(db: Session, deployment_id: UUID) -> Deployment:
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()


def _append_event(
    db: Session,
    deployment_id: UUID,
    message: str,
    level: DeploymentEventLevel = DeploymentEventLevel.INFO,
) -> None:
    db.add(
        DeploymentEvent(
            deployment_id=deployment_id,
            level=level,
            message=message,
        )
    )


@router.post(
    "/topologies/{topology_id}/deploy",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deploy topology",
    response_description="New deployment with nested audit events from the runtime provider.",
)
def deploy_topology(
    topology_id: UUID,
    body: TopologyDeployRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment | JSONResponse:
    """Run deployment against the topology's runtime target (real Docker when target is docker)."""
    mode = body.network_allocation_mode if body else None
    out = topology_deploy_execution.execute_topology_deploy(
        db, user, topology_id, network_allocation_mode=mode
    )
    if isinstance(out, JSONResponse):
        return out
    return out


@router.post(
    "/deployments/{deployment_id}/destroy",
    response_model=DeploymentResponse,
    summary="Destroy deployment",
    response_description="Deployment marked stopped after provider teardown; related events appended.",
)
def destroy_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment:
    """Remove Docker resources labeled for this topology and mark deployment stopped."""
    dep = require_deployment_editor(db, user, deployment_id)
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )

    provider = runtime_provider_for_topology(dep.runtime_target)

    already_stopped = dep.status == DeploymentStatus.STOPPED
    if already_stopped:
        _append_event(
            db,
            dep.id,
            "Destroy requested: deployment already stopped; running label-based Docker cleanup.",
            DeploymentEventLevel.INFO,
        )
    else:
        dep.status = DeploymentStatus.STOPPING
        _append_event(db, dep.id, "Deployment stopping — tearing down runtime resources.")
        db.flush()

    rows = provider.destroy(topo.id, dep.id, project_id=topo.project_id)

    db.execute(
        delete(DeploymentRuntimeResource).where(
            DeploymentRuntimeResource.deployment_id == dep.id
        )
    )

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=level,
                message=msg,
            )
        )

    dep.status = DeploymentStatus.STOPPED
    dep.finished_at = datetime.now(UTC)
    if already_stopped:
        _append_event(
            db,
            dep.id,
            "Destroy idempotent: deployment was already stopped; cleanup events recorded.",
            DeploymentEventLevel.INFO,
        )
    else:
        _append_event(
            db,
            dep.id,
            "Deployment stopped — runtime resources destroyed (best-effort).",
            DeploymentEventLevel.INFO,
        )
    db.commit()

    return _load_deployment_full(db, deployment_id)


@router.post(
    "/deployments/{deployment_id}/runtime/cleanup",
    summary="Engine-only runtime cleanup",
    response_description="Runs provider label-based teardown; does not change deployment status.",
)
def runtime_engine_cleanup(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Best-effort Docker/Kubernetes cleanup for this deployment without stopping it in the database."""
    dep = require_deployment_editor(db, user, deployment_id)
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )

    provider = runtime_provider_for_topology(dep.runtime_target)
    rows = provider.destroy(topo.id, dep.id, project_id=topo.project_id)

    for level, msg in rows:
        db.add(
            DeploymentEvent(
                deployment_id=dep.id,
                level=level,
                message=msg,
            )
        )
    db.add(
        DeploymentEvent(
            deployment_id=dep.id,
            level=DeploymentEventLevel.INFO,
            message="Runtime cleanup invoked (engine resources only; deployment status unchanged).",
        )
    )
    db.commit()

    return {
        "ok": True,
        "deployment_id": str(dep.id),
        "events": [{"level": level.value, "message": msg} for level, msg in rows],
    }


def _deployment_runtime_snapshot(db: Session, deployment_id: UUID) -> RuntimeDeploymentResponse:
    try:
        return runtime_svc.build_deployment_runtime(
            db,
            deployment_id,
            emit_inspection_event=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None


def _runner_http_exception(exc: httpx.HTTPStatusError) -> HTTPException:
    raw = (exc.response.text or "").strip()
    detail = raw
    try:
        j = exc.response.json()
        if isinstance(j, dict):
            detail = str(
                j.get("message")
                or j.get("logs")
                or j.get("output")
                or j.get("detail")
                or raw
            )
    except ValueError:
        pass
    detail = detail[:4000]
    c = exc.response.status_code
    if c == status.HTTP_404_NOT_FOUND:
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=detail)
    if c == status.HTTP_503_SERVICE_UNAVAILABLE:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if c >= 500:
        return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=detail)
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get(
    "/deployments/{deployment_id}/runtime/logs",
    response_model=RuntimeOperationsLogsResponse,
    summary="Aggregated runtime logs for deployment workloads",
)
def get_deployment_runtime_logs(
    deployment_id: UUID,
    tail: int = Query(100, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeOperationsLogsResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_ops.fetch_runtime_deployment_logs(db, deployment_id, tail=tail)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    except httpx.HTTPStatusError as exc:
        raise _runner_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/services/{service_id}/logs",
    response_model=RuntimeOperationsLogsResponse,
    summary="Runtime logs for one persisted service/node resource row",
)
def get_deployment_runtime_service_logs(
    deployment_id: UUID,
    service_id: UUID,
    tail: int = Query(100, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeOperationsLogsResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_ops.fetch_runtime_service_logs(db, deployment_id, service_id, tail=tail)
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in msg.lower() or "no workload" in msg.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(code, detail=msg or "Not found") from exc
    except httpx.HTTPStatusError as exc:
        raise _runner_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    db.commit()
    return body


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/health-check",
    response_model=RuntimeOperationsHealthResponse,
    summary="Run an in-network HTTP health probe against a workload",
)
def post_deployment_runtime_service_health(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeOperationsHealthResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        body = runtime_ops.run_runtime_health_check(db, deployment_id, service_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise _runner_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    db.commit()
    return body


@router.post(
    "/deployments/{deployment_id}/runtime/traffic-tests",
    response_model=RuntimeOperationsTrafficResponse,
    summary="Run ping or HTTP traffic from a source workload (Go runner in-network)",
)
def post_deployment_runtime_traffic_tests(
    deployment_id: UUID,
    payload: RuntimeOperationsTrafficRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeOperationsTrafficResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        body = runtime_ops.run_runtime_traffic_test(db, deployment_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise _runner_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    db.commit()
    return body


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/exec",
    response_model=RuntimeExecResultResponse,
    summary="Run a safe allowlisted diagnostic command inside a workload (Go runner)",
)
def post_deployment_runtime_service_exec(
    deployment_id: UUID,
    service_id: UUID,
    payload: RuntimeExecRequestBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeExecResultResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        out = runtime_exec_svc.run_safe_exec(
            db,
            user.id,
            deployment_id,
            service_id,
            payload.command,
            payload.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    db.commit()
    return out


@router.get(
    "/deployments/{deployment_id}/runtime/exec-results",
    response_model=RuntimeExecResultListResponse,
    summary="Recent safe exec results for a deployment",
)
def list_deployment_runtime_exec_results(
    deployment_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeExecResultListResponse:
    get_deployment_for_user(db, user, deployment_id)
    body = runtime_exec_svc.list_exec_results(db, deployment_id, limit=limit)
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/exec-results/{exec_result_id}",
    response_model=RuntimeExecResultResponse,
    summary="One persisted safe exec result",
)
def get_deployment_runtime_exec_result(
    deployment_id: UUID,
    exec_result_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeExecResultResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        out = runtime_exec_svc.get_exec_result(db, deployment_id, exec_result_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exec result not found",
        ) from None
    db.commit()
    return out


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/restart",
    response_model=RuntimeRestartResponse,
    summary="Restart workload container or pod (Go runner)",
)
def post_deployment_runtime_service_restart(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeRestartResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        out = runtime_exec_svc.run_restart(db, deployment_id, service_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    db.commit()
    return out


@router.get(
    "/deployments/{deployment_id}/runtime/nodes",
    response_model=RuntimeDeploymentSectionResponse,
    summary="Persisted runtime node resources for a deployment",
)
def get_deployment_runtime_nodes(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentSectionResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_nodes_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/services",
    response_model=RuntimeDeploymentServicesSectionResponse,
    summary="Persisted runtime service resources for a deployment",
)
def get_deployment_runtime_services(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentServicesSectionResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_services_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/exposures",
    response_model=ServiceExposureListResponse,
    summary="List service exposure records for a deployment",
)
def list_service_exposures(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceExposureListResponse:
    get_deployment_for_user(db, user, deployment_id)
    rows = exposure_svc.list_exposure_rows(db, deployment_id)
    db.commit()
    return ServiceExposureListResponse(
        deployment_id=deployment_id,
        exposures=[ServiceExposureResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/expose",
    response_model=ServiceExposureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Expose a persisted runtime service row",
    response_model_by_alias=True,
)
def expose_runtime_service(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payload: ServiceExposureCreate | None = Body(None),
) -> ServiceExposureResponse:
    dep = require_deployment_editor(db, user, deployment_id)
    try:
        row = exposure_svc.create_exposure(
            db,
            dep,
            service_id,
            ttl_hours=payload.ttl_hours if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    except DuplicateExposureError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active exposure already exists for this service resource.",
        ) from exc
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/deployments/{deployment_id}/runtime/services/{service_id}/expose",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an active service exposure",
)
def unexpose_runtime_service(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    dep = require_deployment_editor(db, user, deployment_id)
    try:
        ok = exposure_svc.remove_exposure(db, dep, service_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active exposure for this service resource.",
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/deployments/{deployment_id}/runtime/integration",
    response_model=DeploymentIntegrationResponse,
    summary="Use this deployment — endpoints, env vars, and copy-paste snippets",
)
def get_deployment_runtime_integration(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentIntegrationResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = integration_svc.build_deployment_integration(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/integration-outputs",
    response_model=DeploymentIntegrationOutputsResponse,
    summary="Integration outputs for apps, CI/CD, Docker Compose, and Kubernetes",
)
def get_deployment_integration_outputs(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentIntegrationOutputsResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = integration_outputs_svc.build_deployment_integration_outputs(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/integration-outputs/files",
    response_model=list[IntegrationOutputFileItem],
    summary="Download manifest for integration output files",
)
def list_deployment_integration_output_files(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[IntegrationOutputFileItem]:
    get_deployment_for_user(db, user, deployment_id)
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    db.commit()
    return integration_outputs_svc.build_integration_output_file_manifest(deployment_id)


@router.get(
    "/deployments/{deployment_id}/integration-outputs/files/{file_name}",
    summary="Download a single integration output file",
)
def download_deployment_integration_output_file(
    deployment_id: UUID,
    file_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    get_deployment_for_user(db, user, deployment_id)
    try:
        spec, content = integration_outputs_svc.get_integration_output_file(db, deployment_id, file_name)
    except ValueError as exc:
        if str(exc) == "invalid file name":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name") from None
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found") from None
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from None
    db.commit()
    return Response(
        content=content.encode("utf-8"),
        media_type=spec.media_type,
        headers={"Content-Disposition": f'attachment; filename="{spec.name}"'},
    )


@router.get(
    "/deployments/{deployment_id}/integration-outputs/archive",
    summary="Download all integration output files as a zip archive",
)
def download_deployment_integration_outputs_archive(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    get_deployment_for_user(db, user, deployment_id)
    try:
        payload = integration_outputs_svc.build_integration_outputs_archive(db, deployment_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found") from None
    db.commit()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="cns-integration-outputs.zip"'},
    )


@router.get(
    "/deployments/{deployment_id}/runtime/mapping",
    response_model=DeploymentRuntimeMappingResponse,
    summary="Topology node to runtime resource mapping",
)
def get_deployment_runtime_mapping(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentRuntimeMappingResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = integration_svc.build_deployment_runtime_mapping(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.post(
    "/deployments/{deployment_id}/runtime/services/{service_id}/terminal",
    response_model=TerminalSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open an interactive terminal session for a runtime service",
)
def post_deployment_runtime_service_terminal(
    deployment_id: UUID,
    service_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TerminalSessionCreateResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        body = terminal_svc.create_terminal_session(
            db, user.id, deployment_id, service_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Not found",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime/instructions",
    response_model=RuntimeInstructionsOnlyResponse,
    summary="Integration instructions for using this deployment",
)
def get_deployment_runtime_instructions(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeInstructionsOnlyResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        body = runtime_svc.build_deployment_runtime_instructions_section(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/runtime",
    response_model=RuntimeDeploymentResponse,
    summary="Deployment runtime snapshot",
)
def get_deployment_runtime(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeDeploymentResponse:
    get_deployment_for_user(db, user, deployment_id)
    body = _deployment_runtime_snapshot(db, deployment_id)
    db.commit()
    return body


@router.get(
    "/deployments/{deployment_id}/events",
    response_model=list[DeploymentEventResponse],
    summary="List deployment events",
    response_description="Append-only audit timeline for provisioning, inspection, and remediation.",
)
def list_deployment_events(
    deployment_id: UUID,
    user: User = Depends(get_current_user),
    order: str = Query(
        default="asc",
        description="Sort order by created_at: asc (oldest first, default) or desc (newest first).",
        pattern="^(asc|desc)$",
    ),
    level: DeploymentEventLevel | None = Query(
        default=None,
        description="When set, only events with this severity are returned.",
    ),
    q: str | None = Query(
        default=None,
        max_length=500,
        description="Case-insensitive substring filter on message.",
    ),
    db: Session = Depends(get_db),
) -> list[DeploymentEvent]:
    get_deployment_for_user(db, user, deployment_id)
    stmt = select(DeploymentEvent).where(DeploymentEvent.deployment_id == deployment_id)
    if level is not None:
        stmt = stmt.where(DeploymentEvent.level == level)
    if q and q.strip():
        stmt = stmt.where(DeploymentEvent.message.ilike(f"%{q.strip()}%"))
    if order == "desc":
        stmt = stmt.order_by(DeploymentEvent.created_at.desc())
    else:
        stmt = stmt.order_by(DeploymentEvent.created_at.asc())
    return list(db.scalars(stmt).all())


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentResponse,
    summary="Get deployment",
)
def get_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Deployment:
    dep = get_deployment_for_user(db, user, deployment_id)
    stmt = (
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.events))
    )
    return db.execute(stmt).scalar_one()
