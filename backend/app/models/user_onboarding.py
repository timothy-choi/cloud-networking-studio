"""Per-user onboarding progress for first-run guidance (Step 46)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UserOnboarding(Base):
    """One row per user — tracks dismissed checklist and manually completed steps."""

    __tablename__ = "user_onboarding"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    has_seen_onboarding: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_steps: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    user: Mapped["User"] = relationship(back_populates="onboarding")
