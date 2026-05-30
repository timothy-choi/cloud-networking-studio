"""Persisted external deployment state after remote apply (Step 57B)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment_target import DeploymentTarget
    from app.models.external_deployment_job import ExternalDeploymentJob
    from app.models.project import Project
    from app.models.topology import Topology


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExternalDeployment(Base):
    """Active or historical deployment on an external target."""

    __tablename__ = "external_deployments"

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
    target_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployment_targets.id", ondelete="CASCADE"),
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("external_deployment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    compose_project_name: Mapped[str] = mapped_column(String(128))
    remote_workdir: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    services_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )
    destroyed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="external_deployments")
    topology: Mapped["Topology"] = relationship(back_populates="external_deployments")
    target: Mapped["DeploymentTarget"] = relationship(back_populates="external_deployments")
    job: Mapped["ExternalDeploymentJob | None"] = relationship(
        back_populates="external_deployments",
        foreign_keys=[job_id],
    )
