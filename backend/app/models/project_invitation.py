"""Pending project invitations (Step 54B)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectInvitation(Base):
    """Email invitation to join a project; raw token is never stored."""

    __tablename__ = "project_invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    project: Mapped["Project"] = relationship(back_populates="invitations")
    invited_by: Mapped["User"] = relationship(
        foreign_keys=[invited_by_user_id],
        back_populates="sent_project_invitations",
    )
    accepted_by: Mapped["User | None"] = relationship(
        foreign_keys=[accepted_by_user_id],
        back_populates="accepted_project_invitations",
    )
