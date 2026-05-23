"""Deployment operation timeline helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models.deployment_timeline import DeploymentTimelineEvent, TimelineEventType


def record_timeline_event(
    db: Session,
    *,
    deployment_id: UUID,
    event_type: TimelineEventType | str,
    message: str,
    status: str = "info",
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> DeploymentTimelineEvent:
    et = event_type.value if isinstance(event_type, TimelineEventType) else str(event_type)
    rid = request_id or get_request_id()
    row = DeploymentTimelineEvent(
        deployment_id=deployment_id,
        event_type=et,
        status=status,
        message=message,
        request_id=str(rid) if rid else None,
        metadata_json=metadata,
    )
    db.add(row)
    return row


def list_timeline_events(db: Session, deployment_id: UUID) -> list[DeploymentTimelineEvent]:
    stmt = (
        select(DeploymentTimelineEvent)
        .where(DeploymentTimelineEvent.deployment_id == deployment_id)
        .order_by(DeploymentTimelineEvent.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
