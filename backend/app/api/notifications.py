"""Notification inbox routes (Step 54A)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services import notification_service as notify_svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_response(row) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        user_id=row.user_id,
        project_id=row.project_id,
        type=row.type,
        title=row.title,
        message=row.message,
        status=row.status,
        severity=row.severity,
        metadata=row.metadata_json,
        created_at=row.created_at,
        read_at=row.read_at,
    )


@router.get("", response_model=list[NotificationResponse], summary="List my notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationResponse]:
    rows = notify_svc.list_notifications(
        db, user.id, limit=limit, offset=offset, include_archived=include_archived
    )
    db.commit()
    return [_to_response(r) for r in rows]


@router.get("/unread-count", response_model=UnreadCountResponse, summary="Unread notification count")
def get_unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCountResponse:
    count = notify_svc.unread_count(db, user.id)
    db.commit()
    return UnreadCountResponse(unread_count=count)


@router.post("/{notification_id}/read", response_model=NotificationResponse, summary="Mark notification read")
def post_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationResponse:
    try:
        row = notify_svc.mark_read(db, user.id, notification_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.post("/read-all", summary="Mark all notifications read")
def post_notifications_read_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    count = notify_svc.mark_all_read(db, user.id)
    db.commit()
    return {"marked_read": count}


@router.post("/{notification_id}/archive", response_model=NotificationResponse, summary="Archive notification")
def post_notification_archive(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationResponse:
    try:
        row = notify_svc.archive_notification(db, user.id, notification_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    db.commit()
    db.refresh(row)
    return _to_response(row)
