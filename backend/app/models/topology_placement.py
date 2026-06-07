"""Persisted topology placement plans and constraints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.topology import Topology
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TopologyPlacementConstraint(Base):
    __tablename__ = "topology_placement_constraints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), index=True
    )
    constraint_type: Mapped[str] = mapped_column(String(32), index=True)
    node_a: Mapped[str] = mapped_column(String(255))
    node_b: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_host: Mapped[int | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    project: Mapped["Project"] = relationship()
    topology: Mapped["Topology"] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])


class TopologyPlacementPlan(Base):
    __tablename__ = "topology_placement_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("topologies.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    placement_mode: Mapped[str] = mapped_column(String(32), default="first_fit", index=True)
    machine_type: Mapped[str] = mapped_column(String(64))
    host_count: Mapped[int] = mapped_column(default=0)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    project: Mapped["Project"] = relationship()
    topology: Mapped["Topology"] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
