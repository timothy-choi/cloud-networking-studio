"""Topology graph models: network design intent independent of runtime."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment import Deployment


class TopologyStatus(str, enum.Enum):
    """Lifecycle state of a topology definition."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class NodeType(str, enum.Enum):
    """Semantic role of a node within an experimental topology."""

    GENERIC = "generic"
    ROUTER = "router"
    SWITCH = "switch"
    HOST = "host"
    GATEWAY = "gateway"


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Store enums as VARCHAR for simpler DDL before Alembic migrations."""
    return Enum(enum_cls, native_enum=False, length=32)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Topology(Base):
    """User-defined topology (nodes/links) and deployment intent."""

    __tablename__ = "topologies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TopologyStatus] = mapped_column(
        _enum_column(TopologyStatus),
        default=TopologyStatus.DRAFT,
    )
    # e.g. "docker", "kubernetes" — aligns with pluggable runtime providers.
    runtime_target: Mapped[str] = mapped_column(String(64))
    networking_mode: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
    )

    nodes: Mapped[list[TopologyNode]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    links: Mapped[list[TopologyLink]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    deployments: Mapped[list[Deployment]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TopologyNode(Base):
    """A vertex in the topology graph (workload or network element)."""

    __tablename__ = "topology_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    node_type: Mapped[NodeType] = mapped_column(_enum_column(NodeType))
    image: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    config: Mapped[dict | None] = mapped_column(JSON)

    topology: Mapped[Topology] = relationship(back_populates="nodes")
    outgoing_links: Mapped[list[TopologyLink]] = relationship(
        "TopologyLink",
        foreign_keys="TopologyLink.source_node_id",
        back_populates="source_node",
        passive_deletes=True,
    )
    incoming_links: Mapped[list[TopologyLink]] = relationship(
        "TopologyLink",
        foreign_keys="TopologyLink.target_node_id",
        back_populates="target_node",
        passive_deletes=True,
    )


class TopologyLink(Base):
    """An edge between two nodes (L2/L3 attachment or tunnel abstraction)."""

    __tablename__ = "topology_links"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topology_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topologies.id", ondelete="CASCADE"),
        index=True,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    network_name: Mapped[str] = mapped_column(String(255))
    cidr: Mapped[str | None] = mapped_column(String(64))
    gateway: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Optional IPv4 gateway for this segment (defaults to first usable in CIDR when omitted)."""
    vlan_tag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Optional VLAN tag for documentation / future drivers (not applied to default Linux bridge)."""
    source_endpoint_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """IPv4 for source node on this link; falls back to node ip_address when unique enough."""
    target_endpoint_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON)

    topology: Mapped[Topology] = relationship(back_populates="links")
    source_node: Mapped[TopologyNode] = relationship(
        foreign_keys=[source_node_id],
        back_populates="outgoing_links",
    )
    target_node: Mapped[TopologyNode] = relationship(
        foreign_keys=[target_node_id],
        back_populates="incoming_links",
    )
