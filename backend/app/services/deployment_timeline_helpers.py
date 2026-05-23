"""Map runner/deployment log lines to structured timeline events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.deployment_timeline import TimelineEventType
from app.services.deployment_timeline_service import record_timeline_event


def timeline_from_runner_message(
    db: Session,
    *,
    deployment_id: UUID,
    message: str,
) -> None:
    m = message.lower()
    if "node container creation" in m or "node created" in m or "pod created" in m:
        record_timeline_event(
            db,
            deployment_id=deployment_id,
            event_type=TimelineEventType.NODE_CREATED,
            message=message,
            status="info",
        )
    elif "service created" in m or "service scheduled" in m:
        record_timeline_event(
            db,
            deployment_id=deployment_id,
            event_type=TimelineEventType.SERVICE_CREATED,
            message=message,
            status="info",
        )
    elif "health" in m and ("check" in m or "passed" in m or "failed" in m):
        status = "failed" if "fail" in m else "info"
        record_timeline_event(
            db,
            deployment_id=deployment_id,
            event_type=TimelineEventType.HEALTH_CHECKED,
            message=message,
            status=status,
        )


def record_exposed_timeline(
    db: Session,
    *,
    deployment_id: UUID,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_timeline_event(
        db,
        deployment_id=deployment_id,
        event_type=TimelineEventType.EXPOSED,
        message=message,
        status="info",
        metadata=metadata,
    )
