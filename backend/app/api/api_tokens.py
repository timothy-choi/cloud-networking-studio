"""Personal API tokens for CLI and CI (Step 44)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.api_token import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenResponse
from app.services import api_token_service as api_token_svc

router = APIRouter(tags=["api-tokens"])


@router.post(
    "/api-tokens",
    response_model=ApiTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API token",
)
def post_api_token(
    body: ApiTokenCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiTokenCreateResponse:
    out = api_token_svc.create_token(db, user, body)
    db.commit()
    return out


@router.get(
    "/api-tokens",
    response_model=list[ApiTokenResponse],
    summary="List API tokens",
)
def list_api_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApiTokenResponse]:
    rows = api_token_svc.list_tokens(db, user)
    db.commit()
    return rows


@router.delete(
    "/api-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API token",
)
def delete_api_token(
    token_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        api_token_svc.revoke_token(db, user, token_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
