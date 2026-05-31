"""User-owned cloud credential profiles for infrastructure deployments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CredentialProfile(Base):
    """Encrypted cloud credentials scoped to a project."""

    __tablename__ = "credential_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    gcp_project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    credential_type: Mapped[str] = mapped_column(String(64))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    validation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    project: Mapped["Project"] = relationship()
    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
