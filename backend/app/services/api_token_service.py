"""Create and revoke personal API tokens (Step 44, scopes Step 53D)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api_token_scopes import normalize_scopes, parse_stored_scopes, serialize_scopes
from app.core.security import hash_api_token_secret
from app.models.api_token import ApiToken
from app.models.user import User
from app.schemas.api_token import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenResponse


def _scopes_for_response(raw: str | None) -> list[str] | None:
    """Map DB value to API response; NULL means legacy full access."""
    parsed = parse_stored_scopes(raw)
    if parsed is None:
        return None
    return sorted(parsed)


def list_tokens(db: Session, user: User) -> list[ApiTokenResponse]:
    rows = list(
        db.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == user.id)
            .order_by(ApiToken.created_at.desc())
        ).all()
    )
    return [
        ApiTokenResponse(
            id=r.id,
            name=r.name,
            token_hint=r.token_hint,
            scopes=_scopes_for_response(r.scopes_json),
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


def create_token(db: Session, user: User, body: ApiTokenCreateRequest) -> ApiTokenCreateResponse:
    from app.services.quota_service import ensure_api_token_quota

    ensure_api_token_quota(db, user.id)
    try:
        scopes = normalize_scopes(body.scopes)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    secret = secrets.token_urlsafe(32)
    row = ApiToken(
        user_id=user.id,
        name=body.name.strip(),
        token_hash="",
        token_hint=secret[-4:] if len(secret) >= 4 else secret,
        scopes_json=serialize_scopes(scopes),
    )
    db.add(row)
    db.flush()
    row.token_hash = hash_api_token_secret(secret)
    plaintext = f"{row.id}.{secret}"
    db.flush()
    return ApiTokenCreateResponse(
        id=row.id,
        name=row.name,
        token_hint=row.token_hint,
        scopes=_scopes_for_response(row.scopes_json),
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        token=plaintext,
    )


def revoke_token(db: Session, user: User, token_id: UUID) -> None:
    row = db.get(ApiToken, token_id)
    if row is None or row.user_id != user.id:
        raise ValueError("not found")
    if row.revoked_at is not None:
        return
    row.revoked_at = datetime.now(UTC)
