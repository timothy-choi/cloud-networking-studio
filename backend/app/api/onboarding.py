"""First-run onboarding and guided demo endpoints (Step 46)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingCompleteStepRequest,
    OnboardingStatusResponse,
    OnboardingStatusUpdate,
    StartDemoResponse,
)
from app.services import onboarding_service as onboarding_svc

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatusResponse, summary="Get onboarding checklist state")
def get_onboarding_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingStatusResponse:
    return onboarding_svc.build_status_response(db, user)


@router.post("/status", response_model=OnboardingStatusResponse, summary="Update onboarding flags / manual steps")
def post_onboarding_status(
    body: OnboardingStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingStatusResponse:
    return onboarding_svc.update_onboarding_status(db, user, body)


@router.post(
    "/complete-step",
    response_model=OnboardingStatusResponse,
    summary="Mark a checklist step complete (manual override)",
)
def post_onboarding_complete_step(
    body: OnboardingCompleteStepRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingStatusResponse:
    try:
        return onboarding_svc.complete_onboarding_step(db, user, body.step)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/reset", response_model=OnboardingStatusResponse, summary="Reset onboarding progress")
def post_onboarding_reset(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingStatusResponse:
    return onboarding_svc.reset_onboarding(db, user)


@router.post(
    "/start-demo",
    response_model=StartDemoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="One-click demo: demo project, starter template topology, deploy",
    responses={400: {"description": "Topology validation failed for deploy (same body as deployment detail)."}},
)
def post_start_demo(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StartDemoResponse | JSONResponse:
    out = onboarding_svc.start_demo(db, user)
    if isinstance(out, JSONResponse):
        return out
    return out
