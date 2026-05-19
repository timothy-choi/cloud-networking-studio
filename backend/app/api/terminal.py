"""Interactive terminal session WebSocket and close routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.runtime_terminal import TerminalSessionCloseResponse
from app.services import runtime_terminal_service as term_svc

router = APIRouter(tags=["terminal"])


def _user_from_ws_token(db: Session, token: str | None) -> User:
    from app.api.deps import _user_from_token
    from app.core.config import settings
    from app.db.bootstrap import get_or_create_dev_user

    if not token or not str(token).strip():
        if settings.auth_require_login:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        return get_or_create_dev_user(db)
    try:
        return _user_from_token(db, str(token).strip())
    except HTTPException:
        if settings.auth_require_login:
            raise
        return get_or_create_dev_user(db)


@router.delete(
    "/terminal-sessions/{session_id}",
    response_model=TerminalSessionCloseResponse,
    summary="Close an interactive terminal session",
)
def delete_terminal_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TerminalSessionCloseResponse:
    try:
        out = term_svc.close_terminal_session(db, user.id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    db.commit()
    return out


@router.websocket("/terminal-sessions/{session_id}/ws")
async def terminal_session_websocket(
    websocket: WebSocket,
    session_id: UUID,
    token: str | None = Query(None),
) -> None:
    db = SessionLocal()
    try:
        try:
            user = _user_from_ws_token(db, token)
        except HTTPException:
            await websocket.close(code=4401)
            return
        await term_svc.handle_terminal_websocket(websocket, db, user.id, session_id)
    finally:
        db.close()
