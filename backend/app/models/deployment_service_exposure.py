"""User-requested external reachability hints for a persisted runtime service row."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.deployment import Deployment
    from app.models.deployment_runtime_resource import DeploymentRuntimeResource


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeploymentServiceExposure(Base):
    """Tracks how a topology service may be reached outside the cluster/bridge."""

    __tablename__ = "deployment_service_exposures"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        index=True,
    )
    runtime_resource_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployment_runtime_resources.id", ondelete="CASCADE"),
        index=True,
    )
    exposure_type: Mapped[str] = mapped_column(
        String(64),
        doc="port_forward | docker_host_port | kubernetes_service | ingress_placeholder",
    )
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_host: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), doc="active | expired | removed | failed"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exposure_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "exposure_metadata", JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    deployment: Mapped["Deployment"] = relationship(back_populates="service_exposures")
    runtime_resource: Mapped["DeploymentRuntimeResource"] = relationship(
        back_populates="exposures",
    )
