"""Platform observability metrics (Step 53C)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.platform_metrics import (
    DeploymentMetricsResponse,
    PlatformMetricsResponse,
    ProjectMetricsResponse,
)
from app.services.access_control import get_deployment_for_user, get_project_for_member
from app.services.platform_metrics_service import (
    build_deployment_metrics,
    build_platform_metrics,
    build_project_metrics,
)

router = APIRouter(tags=["metrics"])


@router.get(
    "/platform/metrics",
    response_model=PlatformMetricsResponse,
    summary="Platform-wide metrics for the current user",
)
def get_platform_metrics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlatformMetricsResponse:
    return build_platform_metrics(db, user_id=user.id)


@router.get(
    "/projects/{project_id}/metrics",
    response_model=ProjectMetricsResponse,
    summary="Project-scoped platform metrics",
)
def get_project_metrics(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMetricsResponse:
    get_project_for_member(db, user, project_id)
    return build_project_metrics(db, project_id=project_id, user_id=user.id)


@router.get(
    "/deployments/{deployment_id}/metrics",
    response_model=DeploymentMetricsResponse,
    summary="Deployment-scoped platform metrics",
)
def get_deployment_metrics(
    deployment_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentMetricsResponse:
    get_deployment_for_user(db, user, deployment_id)
    try:
        return build_deployment_metrics(db, deployment_id=deployment_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found") from None
