"""Infrastructure deployment API routes (Step 57C)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.infrastructure_deployment import (
    InfrastructureDeploymentConfirmRequest,
    InfrastructureDeploymentCreate,
    InfrastructureDeploymentDestroyRequest,
    InfrastructureDeploymentForceCleanupRequest,
    InfrastructureDeploymentListResponse,
    InfrastructureDeploymentResponse,
    InfrastructureExecutionListResponse,
    InfrastructureExecutionResponse,
    InfrastructureTemplateInfo,
    InfrastructureTemplateListResponse,
)
from app.services import infra_deployment_phases as infra_phases
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services import infrastructure_deployment_service as infra_svc
from app.services.infra_apply_safety import InfraApplySafetyError, InfraInvalidStateError
from app.services.infra_template_registry import list_templates
from app.runtime.infra_runner_client import InfraRunnerClientError

router = APIRouter(tags=["infrastructure-deployments"])


def _to_deployment(row) -> InfrastructureDeploymentResponse:
    return InfrastructureDeploymentResponse(
        id=str(row.id),
        project_id=str(row.project_id),
        topology_id=str(row.topology_id),
        name=row.name,
        stack_type=row.stack_type,
        template_id=row.template_id,
        provider=row.provider,
        status=row.status,
        variables_json=row.variables_json or {},
        plan_summary_json=row.plan_summary_json,
        outputs_json=row.outputs_json or {},
        inventory_json=row.inventory_json or {},
        state_metadata_json=infra_phases.enrich_state_metadata(row),
        events_json=row.events_json or [],
        metrics_json=row.metrics_json or {},
        runtime_targets_json=row.runtime_targets_json or [],
        error_message=row.error_message,
        credentials_ref=row.credentials_ref,
        placement_plan_id=str(row.placement_plan_id) if getattr(row, "placement_plan_id", None) else None,
        confirmed_at=row.confirmed_at,
        confirmed_by_user_id=str(row.confirmed_by_user_id) if row.confirmed_by_user_id else None,
        created_by_user_id=str(row.created_by_user_id) if row.created_by_user_id else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        destroyed_at=row.destroyed_at,
    )


def _to_execution(row) -> InfrastructureExecutionResponse:
    return InfrastructureExecutionResponse(
        id=str(row.id),
        infrastructure_deployment_id=str(row.infrastructure_deployment_id),
        execution_type=row.execution_type,
        mode=row.mode,
        status=row.status,
        runner_execution_id=row.runner_execution_id,
        logs=row.logs,
        artifact_refs=row.artifact_refs or [],
        duration_ms=row.duration_ms,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _get_deployment_for_user(db: Session, user: User, deployment_id: UUID):
    deployment = infra_svc.get_deployment(db, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Not found")
    get_topology_for_user(db, user, deployment.topology_id)
    return deployment


@router.get("/infrastructure/templates", response_model=InfrastructureTemplateListResponse)
def list_infrastructure_templates(
    user: User = Depends(get_current_user),
) -> InfrastructureTemplateListResponse:
    _ = user
    items = [
        InfrastructureTemplateInfo(
            template_id=t.template_id,
            provider=t.terraform_dir,
            description=t.description,
            supported_providers=list(t.supported_providers),
        )
        for t in list_templates()
    ]
    return InfrastructureTemplateListResponse(items=items)


@router.get(
    "/topologies/{topology_id}/infrastructure-deployments",
    response_model=InfrastructureDeploymentListResponse,
)
def list_infrastructure_deployments(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentListResponse:
    get_topology_for_user(db, user, topology_id)
    items = [_to_deployment(row) for row in infra_svc.list_deployments_for_topology(db, topology_id)]
    return InfrastructureDeploymentListResponse(items=items)


@router.post(
    "/topologies/{topology_id}/infrastructure-deployments",
    response_model=InfrastructureDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_infrastructure_deployment(
    topology_id: UUID,
    body: InfrastructureDeploymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    require_topology_editor(db, user, topology_id)
    topo = get_topology_for_user(db, user, topology_id)
    try:
        deployment = infra_svc.create_deployment(
            db,
            topology=topo,
            actor=user,
            name=body.name,
            template_id=body.template_id,
            provider=body.provider,
            variables=body.variables,
            credentials_ref=body.credentials_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)


@router.post(
    "/infrastructure-deployments/{deployment_id}/validate",
    response_model=InfrastructureDeploymentResponse,
)
def validate_infrastructure_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    try:
        deployment = infra_svc.run_validate(db, deployment=deployment, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)


@router.post(
    "/infrastructure-deployments/{deployment_id}/plan",
    response_model=InfrastructureDeploymentResponse,
)
def plan_infrastructure_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    try:
        deployment = infra_svc.run_plan(db, deployment=deployment, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)


@router.get(
    "/infrastructure-deployments/{deployment_id}",
    response_model=InfrastructureDeploymentResponse,
)
def get_infrastructure_deployment(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    return _to_deployment(deployment)


@router.get(
    "/infrastructure-deployments/{deployment_id}/executions",
    response_model=InfrastructureExecutionListResponse,
)
def list_infrastructure_executions(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureExecutionListResponse:
    _get_deployment_for_user(db, user, deployment_id)
    items = [_to_execution(row) for row in infra_svc.list_executions(db, deployment_id)]
    return InfrastructureExecutionListResponse(items=items)


@router.post(
    "/infrastructure-deployments/{deployment_id}/confirm",
    response_model=InfrastructureDeploymentResponse,
)
def confirm_infrastructure_deployment(
    deployment_id: UUID,
    body: InfrastructureDeploymentConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")
    if infra_phases.has_terraform_apply_completed(deployment):
        raise HTTPException(
            status_code=409,
            detail={
                "message": infra_phases.APPLY_ALREADY_COMPLETED_MESSAGE,
                "status": deployment.status,
            },
        )
    if deployment.status != "awaiting_confirmation":
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Cannot confirm apply while status is '{deployment.status}'. "
                    "Run Plan first and wait for awaiting_confirmation."
                ),
                "status": deployment.status,
                "expected_status": "awaiting_confirmation",
            },
        )
    try:
        deployment = infra_svc.confirm_and_apply(
            db,
            deployment=deployment,
            actor=user,
            confirmation_text=body.confirmation_text,
            unsafe_testing_override=body.unsafe_testing_override,
        )
    except InfraInvalidStateError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except InfraApplySafetyError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": exc.message, "checklist": exc.checklist},
        ) from exc
    except infra_svc.RealCloudApplyDisabledError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except InfraRunnerClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "runner_status": exc.status_code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    if deployment.status == "failed":
        raise HTTPException(
            status_code=409,
            detail={
                "message": deployment.error_message or "Infrastructure apply failed",
                "status": deployment.status,
                "deployment_id": str(deployment.id),
            },
        )
    return _to_deployment(deployment)


@router.post(
    "/infrastructure-deployments/{deployment_id}/retry-configure",
    response_model=InfrastructureDeploymentResponse,
)
def retry_infrastructure_configuration(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    try:
        deployment = infra_svc.retry_configuration(db, deployment=deployment, actor=user)
    except InfraInvalidStateError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)


@router.post(
    "/infrastructure-deployments/{deployment_id}/destroy",
    response_model=InfrastructureDeploymentResponse,
)
def destroy_infrastructure_deployment(
    deployment_id: UUID,
    body: InfrastructureDeploymentDestroyRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    confirmation_text = body.confirmation_text if body else None
    try:
        deployment = infra_svc.destroy_deployment(
            db,
            deployment=deployment,
            actor=user,
            confirmation_text=confirmation_text,
        )
    except infra_svc.PlanOnlyDestroyDisabledError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)


@router.post(
    "/infrastructure-deployments/{deployment_id}/force-metadata-cleanup",
    response_model=InfrastructureDeploymentResponse,
)
def force_infrastructure_metadata_cleanup(
    deployment_id: UUID,
    body: InfrastructureDeploymentForceCleanupRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    try:
        deployment = infra_svc.force_metadata_cleanup(
            db,
            deployment=deployment,
            actor=user,
            confirmation_text=body.confirmation_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)
