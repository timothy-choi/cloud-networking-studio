"""Manual runtime controller API — status, scheduled reconciliation pass, single-deployment heal."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.controller import (
    ControllerRunOnceResponse,
    ControllerStatusResponse,
    HealingResponse,
    RestartedContainerRef,
)
from app.services import runtime_controller as controller_svc
from app.services.access_control import require_deployment_editor

router = APIRouter(tags=["controller"])


@router.get(
    "/controller/status",
    response_model=ControllerStatusResponse,
    summary="Controller status",
)
def get_controller_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ControllerStatusResponse:
    snap = controller_svc.get_controller_status(db, user_id=user.id)
    return ControllerStatusResponse(
        controller_mode=snap.controller_mode,
        managed_deployments_count=snap.managed_deployments_count,
        active_deployments_count=snap.active_deployments_count,
        supported_providers=list(snap.supported_providers),
        last_run_timestamp=snap.last_run_timestamp,
        health_summary=snap.health_summary,
    )


@router.post(
    "/controller/run-once",
    response_model=ControllerRunOnceResponse,
    summary="Run controller reconcile sweep",
)
def post_controller_run_once(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ControllerRunOnceResponse:
    summary = controller_svc.run_controller_once(db, user_id=user.id)
    db.commit()
    return ControllerRunOnceResponse(
        deployments_checked=summary.deployments_checked,
        drift_detected=summary.drift_detected,
        stopped_containers=summary.stopped_containers,
        missing_containers=summary.missing_containers,
        missing_networks=summary.missing_networks,
    )


@router.post(
    "/deployments/{deployment_id}/heal",
    response_model=HealingResponse,
    summary="Heal deployment",
    response_description="Attempts provider-specific recovery (restarts, recreate paths) after drift.",
)
def post_deployment_heal(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HealingResponse:
    require_deployment_editor(db, user, deployment_id)
    try:
        data = controller_svc.heal_deployment(db, deployment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        ) from None
    db.commit()

    rec = data.reconciliation
    heal = data.healing
    return HealingResponse(
        deployment_id=data.deployment_id,
        topology_id=data.topology_id,
        reconciliation_missing_network=rec.missing_network,
        reconciliation_missing_node_ids=list(rec.missing_node_ids),
        reconciliation_stopped_count=len(rec.stopped_containers),
        restarted_containers=[
            RestartedContainerRef(container_id=cid, name=nm)
            for cid, nm in heal.restarted
        ],
        skipped_missing_resources=data.skipped_missing_resources,
        healing_errors=list(heal.errors),
    )
