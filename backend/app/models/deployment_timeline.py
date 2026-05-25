"""Deployment operation timeline events (Step 53A)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TimelineEventType(str, enum.Enum):
    DEPLOY_REQUESTED = "DEPLOY_REQUESTED"
    DEPLOY_STARTED = "DEPLOY_STARTED"
    NODE_CREATED = "NODE_CREATED"
    SERVICE_CREATED = "SERVICE_CREATED"
    EXPOSED = "EXPOSED"
    HEALTH_CHECKED = "HEALTH_CHECKED"
    DEPLOY_SUCCEEDED = "DEPLOY_SUCCEEDED"
    DEPLOY_FAILED = "DEPLOY_FAILED"
    DESTROY_REQUESTED = "DESTROY_REQUESTED"
    DESTROY_STARTED = "DESTROY_STARTED"
    DESTROY_SUCCEEDED = "DESTROY_SUCCEEDED"
    DESTROY_FAILED = "DESTROY_FAILED"
    CLEANUP_REQUESTED = "CLEANUP_REQUESTED"
    CLEANUP_STARTED = "CLEANUP_STARTED"
    CLEANUP_SUCCEEDED = "CLEANUP_SUCCEEDED"
    CLEANUP_PARTIAL_FAILED = "CLEANUP_PARTIAL_FAILED"
    DEPLOYMENT_MARKED_DESTROYED_AFTER_CLEANUP = "DEPLOYMENT_MARKED_DESTROYED_AFTER_CLEANUP"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=64)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeploymentTimelineEvent(Base):
    __tablename__ = "deployment_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="info")
    message: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, index=True)
