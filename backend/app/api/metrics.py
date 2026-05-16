"""Read-only observability metrics (Step 32)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.metrics import MetricsSummaryResponse
from app.services.metrics_summary import build_metrics_summary

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    summary="Cross-topology metrics summary",
    response_description="Aggregate counts and a short cross-deployment event feed for dashboards.",
)
def get_metrics_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MetricsSummaryResponse:
    """Return topology/deployment/traffic/failure counters and recent deployment events."""
    return build_metrics_summary(db, owner_user_id=user.id)
