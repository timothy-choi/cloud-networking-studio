"""Individual Terraform/Ansible execution records (Step 57C)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.infrastructure_deployment import InfrastructureDeployment


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InfrastructureExecution(Base):
    """One Terraform or Ansible operation dispatched through the Go runner."""

    __tablename__ = "infrastructure_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    infrastructure_deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("infrastructure_deployments.id", ondelete="CASCADE"),
        index=True,
    )
    execution_type: Mapped[str] = mapped_column(String(16), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    runner_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_refs: Mapped[list] = mapped_column(JSON, default=list)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    infrastructure_deployment: Mapped["InfrastructureDeployment"] = relationship(
        back_populates="executions"
    )
