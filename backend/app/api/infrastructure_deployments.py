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
    InfrastructureDeploymentListResponse,
    InfrastructureDeploymentResponse,
    InfrastructureExecutionListResponse,
    InfrastructureExecutionResponse,
    InfrastructureTemplateInfo,
    InfrastructureTemplateListResponse,
)
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services import infrastructure_deployment_service as infra_svc
from app.services.infra_template_registry import list_templates

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
        state_metadata_json=row.state_metadata_json or {},
        events_json=row.events_json or [],
        metrics_json=row.metrics_json or {},
        runtime_targets_json=row.runtime_targets_json or [],
        error_message=row.error_message,
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
        )
        deployment = infra_svc.run_validate_and_plan(db, deployment=deployment, actor=user)
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
    try:
        deployment = infra_svc.confirm_and_apply(db, deployment=deployment, actor=user)
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureDeploymentResponse:
    deployment = _get_deployment_for_user(db, user, deployment_id)
    require_topology_editor(db, user, deployment.topology_id)
    try:
        deployment = infra_svc.destroy_deployment(db, deployment=deployment, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return _to_deployment(deployment)
