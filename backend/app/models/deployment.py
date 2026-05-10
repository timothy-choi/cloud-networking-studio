"""Deployment runs and append-only event stream for a topology."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.topology import Topology


class DeploymentStatus(str, enum.Enum):
    """Coarse-grained state machine for a deployment attempt."""

    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentEventLevel(str, enum.Enum):
    """Severity for deployment log lines stored as relational events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=32)


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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    topology: Mapped[Topology] = relationship(back_populates="deployments")
    events: Mapped[list[DeploymentEvent]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentEvent.created_at",
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
        DateTime(timezone=False), default=datetime.utcnow
    )

    deployment: Mapped[Deployment] = relationship(back_populates="events")
