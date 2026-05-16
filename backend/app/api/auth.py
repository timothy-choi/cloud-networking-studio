"""Authentication: register, login, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse, UserPublic
from app.api.deps import require_bearer_user

router = APIRouter(prefix="/auth", tags=["auth"])

_DEFAULT_WORKSPACE = "My workspace"

_PASSWORD_MIN_BYTES = 8
_PASSWORD_MAX_BYTES = 72  # bcrypt limit (after normalization we stay within this for stored secrets)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_by_email(db: Session, email: str) -> User | None:
    """Load ``User`` by normalized email, or ``None`` if absent.

    Uses ``Session.execute(select(User)).scalar_one_or_none()`` so the ORM always
    returns a mapped ``User`` (or ``None``). ``Session.scalar(select(User))`` can
    route through ``Connection.scalar()`` and return only the **first column**
    (typically the primary-key UUID). Code then did ``user.password_hash`` on
    that UUID, raising::

        AttributeError: 'UUID' object has no attribute 'password_hash'

    which surfaced to clients as **HTTP 500** for unknown emails. Treat any
    non-``User`` scalar as "not found" so invalid logins stay **401** without
    revealing whether the address exists.
    """
    row = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if row is None:
        return None
    return row if isinstance(row, User) else None


def _assert_register_password_policy(password: str) -> None:
    raw = password.encode("utf-8")
    n = len(raw)
    if n < _PASSWORD_MIN_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {_PASSWORD_MIN_BYTES} UTF-8 bytes.",
        )
    if n > _PASSWORD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Password must be at most {_PASSWORD_MAX_BYTES} UTF-8 bytes (bcrypt limit). "
                "Use a shorter password or fewer multi-byte (e.g. emoji) characters."
            ),
        )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _assert_register_password_policy(body.password)
    em = _normalize_email(str(body.email))
    if _user_by_email(db, em) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=em,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(user)
    db.flush()
    db.add(
        Project(
            owner_user_id=user.id,
            name=_DEFAULT_WORKSPACE,
            description="Your first workspace.",
        )
    )
    db.commit()
    db.refresh(user)
    token = create_access_token(user_id=user.id, email=user.email)
    return TokenResponse(
        access_token=token,
        user=UserPublic.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse, summary="Login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    em = _normalize_email(str(body.email))
    user = _user_by_email(db, em)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    ph = user.password_hash
    if not ph:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    try:
        password_ok = verify_password(body.password, ph)
    except Exception:
        # Defense in depth: ``verify_password`` should not raise, but never map
        # verification bugs to HTTP 500 (same opaque 401 as wrong password).
        password_ok = False
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user_id=user.id, email=user.email)
    return TokenResponse(
        access_token=token,
        user=UserPublic.model_validate(user),
    )


@router.get("/me", response_model=MeResponse, summary="Current user (requires Bearer JWT)")
def me(user: User = Depends(require_bearer_user)) -> MeResponse:
    return MeResponse(user=UserPublic.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout (client discards token)")
def logout() -> Response:
    """Stateless JWT: discard the token on the client."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
