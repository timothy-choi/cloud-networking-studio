"""Intentional runtime disruptions for resilience testing (chaos-style)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FailureInjectionFailureType(str, enum.Enum):
    STOP_CONTAINER = "stop_container"
    RESTART_CONTAINER = "restart_container"
    KILL_CONTAINER = "kill_container"


class FailureInjectionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=32)


class FailureInjection(Base):
    """Recorded failure injection attempt against a deployed topology node."""

    __tablename__ = "failure_injections"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    failure_type: Mapped[FailureInjectionFailureType] = mapped_column(
        _enum_column(FailureInjectionFailureType),
    )
    status: Mapped[FailureInjectionStatus] = mapped_column(
        _enum_column(FailureInjectionStatus),
        default=FailureInjectionStatus.PENDING,
    )
    description: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    result_message: Mapped[str | None] = mapped_column(Text)
