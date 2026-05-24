"""Personal API tokens for CLI and CI (Step 44)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_jwt_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.api_token import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenResponse
from app.services import api_token_service as api_token_svc
from app.services.audit_service import record_audit

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
    user: User = Depends(require_jwt_user),
) -> ApiTokenCreateResponse:
    try:
        out = api_token_svc.create_token(db, user, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    record_audit(
        db,
        action="api_token.create",
        resource_type="api_token",
        resource_id=out.id,
        actor_user_id=user.id,
        status="success",
        metadata={"name": body.name, "scopes": body.scopes},
    )
    try:
        from app.services import email_templates as tpl
        from app.services.notification_service import notify_user

        subj, text, html = tpl.api_token_created(token_name=body.name)
        notify_user(
            db,
            user.id,
            type="api_token.created",
            title=f"API token created: {body.name}",
            message=f"A new API token \"{body.name}\" was created.",
            severity="info",
            metadata={"token_id": str(out.id)},
            send_email=True,
            email_subject=subj,
            email_text=text,
            email_html=html,
        )
    except Exception:
        pass
    db.commit()
    return out


@router.get(
    "/api-tokens",
    response_model=list[ApiTokenResponse],
    summary="List API tokens",
)
def list_api_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(require_jwt_user),
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
    user: User = Depends(require_jwt_user),
) -> Response:
    try:
        api_token_svc.revoke_token(db, user, token_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    record_audit(
        db,
        action="api_token.revoke",
        resource_type="api_token",
        resource_id=token_id,
        actor_user_id=user.id,
        status="success",
    )
    try:
        from app.services import email_templates as tpl
        from app.services.notification_service import notify_user

        subj, text, html = tpl.api_token_revoked(token_name=str(token_id))
        notify_user(
            db,
            user.id,
            type="api_token.revoked",
            title="API token revoked",
            message="An API token was revoked on your account.",
            severity="warning",
            metadata={"token_id": str(token_id)},
            send_email=True,
            email_subject=subj,
            email_text=text,
            email_html=html,
        )
    except Exception:
        pass
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
