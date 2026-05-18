"""FastAPI dependencies: DB session, current user, JWT + API tokens."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token, verify_api_token_secret
from app.db.bootstrap import get_or_create_dev_user
from app.db.session import get_db
from app.models.api_token import ApiToken
from app.models.user import User

security = HTTPBearer(auto_error=False)


def _user_from_jwt(db: Session, token: str) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        uid = UUID(sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _user_from_api_token_bearer(db: Session, token: str) -> User | None:
    """Resolve ``{token_id}.{secret}`` (single dot) to a user, or return ``None``."""
    if token.count(".") != 1:
        return None
    left, secret = token.split(".", 1)
    if not left or not secret or len(secret) < 8:
        return None
    try:
        tid = UUID(left)
    except ValueError:
        return None
    row = db.get(ApiToken, tid)
    if row is None or row.revoked_at is not None:
        return None
    if not verify_api_token_secret(secret, row.token_hash):
        return None
    from datetime import UTC, datetime

    row.last_used_at = datetime.now(UTC)
    db.flush()
    db.commit()
    return db.get(User, row.user_id)


def _user_from_token(db: Session, token: str) -> User:
    """JWT (three segments) or personal API token ``uuid.secret``."""
    raw = (token or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if raw.count(".") == 2:
        return _user_from_jwt(db, raw)
    if raw.count(".") == 1:
        u = _user_from_api_token_bearer(db, raw)
        if u is not None:
            return u
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_bearer_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    """Current user from JWT or API token. Used for ``GET /auth/me`` (never the implicit dev user)."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _user_from_token(db, creds.credentials)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    if settings.auth_require_login:
        if creds is None or not creds.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _user_from_token(db, creds.credentials)

    if creds and creds.credentials:
        try:
            return _user_from_token(db, creds.credentials)
        except HTTPException:
            pass
    return get_or_create_dev_user(db)
