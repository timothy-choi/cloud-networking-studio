"""Infrastructure deployment orchestration (Step 57C)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.infrastructure_execution import InfrastructureExecution
    from app.models.project import Project
    from app.models.topology import Topology
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InfrastructureDeployment(Base):
    """End-to-end infrastructure stack: Terraform provision → Ansible configure → runtime ready."""

    __tablename__ = "infrastructure_deployments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    stack_type: Mapped[str] = mapped_column(String(32), default="terraform_ansible")
    template_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    variables_json: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    inventory_json: Mapped[dict] = mapped_column(JSON, default=dict)
    state_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    events_json: Mapped[list] = mapped_column(JSON, default=list)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime_targets_json: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="infrastructure_deployments")
    topology: Mapped["Topology"] = relationship(back_populates="infrastructure_deployments")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    confirmed_by: Mapped["User | None"] = relationship(foreign_keys=[confirmed_by_user_id])
    executions: Mapped[list["InfrastructureExecution"]] = relationship(
        back_populates="infrastructure_deployment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InfrastructureExecution.created_at",
    )
