"""Project-scoped remote deployment targets (Step 57A)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.external_deployment import ExternalDeployment
    from app.models.external_deployment_job import ExternalDeploymentJob
    from app.models.project import Project
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeploymentTarget(Base):
    """External/cloud deployment destination for a project."""

    __tablename__ = "deployment_targets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    credentials_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )

    project: Mapped["Project"] = relationship(back_populates="deployment_targets")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    external_jobs: Mapped[list["ExternalDeploymentJob"]] = relationship(
        back_populates="target",
        passive_deletes=True,
    )
    external_deployments: Mapped[list["ExternalDeployment"]] = relationship(
        back_populates="target",
        passive_deletes=True,
    )
