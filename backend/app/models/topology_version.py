"""Topology version snapshots (Step 56)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.topology import Topology
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TopologyVersion(Base):
    """Immutable snapshot of topology graph + metadata at a point in time."""

    __tablename__ = "topology_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )

    topology: Mapped["Topology"] = relationship(back_populates="versions")
    created_by: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id],
    )
