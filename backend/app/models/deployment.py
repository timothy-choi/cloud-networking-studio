"""Deployment runs and append-only event stream for a topology."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.topology import Topology
    from app.models.deployment_runtime_exec_result import DeploymentRuntimeExecResult
    from app.models.deployment_runtime_resource import DeploymentRuntimeResource
    from app.models.deployment_service_exposure import DeploymentServiceExposure


class DeploymentStatus(str, enum.Enum):
    """Coarse-grained state machine for a deployment attempt."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED = "stopped"


class TopologySyncStatus(str, enum.Enum):
    """Whether deployment config still matches the topology definition."""

    IN_SYNC = "in_sync"
    OUT_OF_SYNC = "out_of_sync"


class DeploymentCleanupStatus(str, enum.Enum):
    """Result of tearing down runtime resources for a deployment."""

    NONE = "none"
    CLEAN = "clean"
    PARTIAL_FAILED = "partial_failed"


class DeploymentEventLevel(str, enum.Enum):
    """Severity for deployment log lines stored as relational events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Persist/load ``str`` enum **values** (e.g. ``none``), not member names (``NONE``)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Deployment(Base):
    """A concrete orchestration run against a topology."""

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[DeploymentStatus] = mapped_column(
        _enum_column(DeploymentStatus),
        default=DeploymentStatus.PENDING,
    )
    runtime_target: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    deployment_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployment_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    effective_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    topology_sync_status: Mapped[TopologySyncStatus] = mapped_column(
        _enum_column(TopologySyncStatus),
        default=TopologySyncStatus.IN_SYNC,
        index=True,
    )
    cleanup_status: Mapped[DeploymentCleanupStatus] = mapped_column(
        _enum_column(DeploymentCleanupStatus),
        default=DeploymentCleanupStatus.NONE,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )

    topology: Mapped[Topology] = relationship(back_populates="deployments")
    events: Mapped[list[DeploymentEvent]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentEvent.created_at",
        passive_deletes=True,
    )
    runtime_resources: Mapped[list["DeploymentRuntimeResource"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    service_exposures: Mapped[list["DeploymentServiceExposure"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    runtime_exec_results: Mapped[list["DeploymentRuntimeExecResult"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DeploymentEvent(Base):
    """Structured audit/event row for a deployment."""

    __tablename__ = "deployment_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        index=True,
    )
    level: Mapped[DeploymentEventLevel] = mapped_column(
        _enum_column(DeploymentEventLevel),
        default=DeploymentEventLevel.INFO,
    )
    message: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )

    deployment: Mapped[Deployment] = relationship(back_populates="events")
