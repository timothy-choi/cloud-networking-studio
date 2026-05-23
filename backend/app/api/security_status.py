"""GET /platform/security-status (Step 53D)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.security_status import SecurityStatusResponse
from app.services.security_status_service import build_security_status

router = APIRouter(tags=["security"])


@router.get(
    "/platform/security-status",
    response_model=SecurityStatusResponse,
    summary="Platform security posture for the current user",
)
def get_platform_security_status(
    _user: User = Depends(get_current_user),
) -> SecurityStatusResponse:
    return build_security_status()
