"""Persisted safe exec results for deployment runtime diagnostics (Step 42)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment import Deployment
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeploymentRuntimeExecResult(Base):
    """One safe exec invocation (allowlisted command) against a runtime resource."""

    __tablename__ = "deployment_runtime_exec_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        index=True,
    )
    runtime_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployment_runtime_resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    command: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    runtime_provider: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )

    deployment: Mapped["Deployment"] = relationship(back_populates="runtime_exec_results")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
