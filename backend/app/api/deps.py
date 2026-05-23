"""FastAPI dependencies: DB session, current user, JWT + API tokens (Step 53D scopes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.api_token_scopes import parse_stored_scopes
from app.core.config import settings
from app.core.security import decode_access_token, verify_api_token_secret
from app.db.bootstrap import get_or_create_dev_user
from app.db.session import get_db
from app.models.api_token import ApiToken
from app.models.user import User
from app.services.api_token_scope_service import ensure_api_token_scope

security = HTTPBearer(auto_error=False)

AuthMethod = Literal["jwt", "api_token", "dev"]


@dataclass
class AuthContext:
    user: User
    auth_method: AuthMethod
    api_token: ApiToken | None = None
    token_scopes: set[str] | None = None


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


def _auth_from_api_token_bearer(db: Session, token: str) -> AuthContext | None:
    """Resolve ``{token_id}.{secret}`` (single dot) to auth context, or return ``None``."""
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
    user = db.get(User, row.user_id)
    if user is None:
        return None
    return AuthContext(
        user=user,
        auth_method="api_token",
        api_token=row,
        token_scopes=parse_stored_scopes(row.scopes_json),
    )


def _auth_from_token(db: Session, token: str) -> AuthContext:
    """JWT (three segments) or personal API token ``uuid.secret``."""
    raw = (token or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if raw.count(".") == 2:
        return AuthContext(user=_user_from_jwt(db, raw), auth_method="jwt")
    if raw.count(".") == 1:
        ctx = _auth_from_api_token_bearer(db, raw)
        if ctx is not None:
            return ctx
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> AuthContext:
    if settings.auth_require_login:
        if creds is None or not creds.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        ctx = _auth_from_token(db, creds.credentials)
    elif creds and creds.credentials:
        try:
            ctx = _auth_from_token(db, creds.credentials)
        except HTTPException:
            ctx = AuthContext(user=get_or_create_dev_user(db), auth_method="dev")
    else:
        ctx = AuthContext(user=get_or_create_dev_user(db), auth_method="dev")

    ensure_api_token_scope(
        auth_method=ctx.auth_method,
        token_scopes=ctx.token_scopes,
        method=request.method,
        path=request.url.path,
    )
    return ctx


def enforce_api_token_scopes(
    request: Request,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    """Global dependency — scope checks run inside :func:`get_auth_context`."""
    _ = ctx


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
    return _auth_from_token(db, creds.credentials).user


def require_jwt_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    """Interactive JWT only — API tokens cannot manage tokens or other JWT-only routes."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ctx = _auth_from_token(db, creds.credentials)
    if ctx.auth_method != "jwt":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "This route requires interactive login (JWT), not an API token.",
            },
        )
    return ctx.user


def get_current_user(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return ctx.user
