"""Traffic tests between topology nodes (reachability / HTTP checks)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment import Deployment
    from app.models.topology import Topology, TopologyNode


class TrafficTestType(str, enum.Enum):
    PING = "ping"
    HTTP = "http"


class TrafficTestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=32)


class TrafficTest(Base):
    """A single traffic experiment from a source node toward a target."""

    __tablename__ = "traffic_tests"

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
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    target_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    test_type: Mapped[TrafficTestType] = mapped_column(_enum_column(TrafficTestType))
    status: Mapped[TrafficTestStatus] = mapped_column(
        _enum_column(TrafficTestStatus),
        default=TrafficTestStatus.PENDING,
    )
    command: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    topology: Mapped["Topology"] = relationship(
        "Topology",
        foreign_keys=[topology_id],
    )
    deployment: Mapped["Deployment | None"] = relationship(
        "Deployment",
        foreign_keys=[deployment_id],
    )
    source_node: Mapped["TopologyNode"] = relationship(
        "TopologyNode",
        foreign_keys=[source_node_id],
    )
    target_node: Mapped["TopologyNode | None"] = relationship(
        "TopologyNode",
        foreign_keys=[target_node_id],
    )
    result: Mapped["TrafficTestResult | None"] = relationship(
        "TrafficTestResult",
        back_populates="traffic_test",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TrafficTestResult(Base):
    """Captured exec outcome for a traffic test."""

    __tablename__ = "traffic_test_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    traffic_test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("traffic_tests.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    exit_code: Mapped[int] = mapped_column(Integer)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow
    )

    traffic_test: Mapped["TrafficTest"] = relationship(
        "TrafficTest",
        back_populates="result",
    )
