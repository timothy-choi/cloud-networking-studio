"""Reusable topology/runtime templates (Step 43)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class TemplateVisibility(str, enum.Enum):
    PRIVATE = "private"
    PROJECT = "project"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RuntimeTemplate(Base):
    """Saved topology graph + runtime intent for cloning or sharing in a project."""

    __tablename__ = "runtime_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(String(16), default=TemplateVisibility.PRIVATE.value)
    topology_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_topology_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="SET NULL"),
        nullable=True,
    )
    slug: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )

    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])
    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id])
