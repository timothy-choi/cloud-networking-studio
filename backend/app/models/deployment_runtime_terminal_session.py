"""Interactive terminal sessions for deployment runtime workloads."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment import Deployment
    from app.models.deployment_runtime_resource import DeploymentRuntimeResource
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeploymentRuntimeTerminalSession(Base):
    __tablename__ = "deployment_runtime_terminal_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        index=True,
    )
    runtime_resource_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployment_runtime_resources.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="opening", index=True)
    runtime_provider: Mapped[str] = mapped_column(String(32), default="docker")
    shell: Mapped[str] = mapped_column(String(128), default="/bin/sh")
    audit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    deployment: Mapped["Deployment"] = relationship()
    runtime_resource: Mapped["DeploymentRuntimeResource"] = relationship()
    user: Mapped["User"] = relationship()
