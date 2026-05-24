"""Optional deploy overrides (defaults come from topology.config)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.services.network_allocation import DEFAULT_NETWORK_ALLOCATION_MODE


class TopologyDeployRequest(BaseModel):
    """Optional deploy overrides (defaults come from topology.config)."""

    network_allocation_mode: str | None = Field(
        default=None,
        description="`managed` (Docker assigns runtime IPs) or `intent` (honor static topology IPs).",
        examples=[DEFAULT_NETWORK_ALLOCATION_MODE, "intent"],
    )
    profile_id: UUID | None = Field(
        default=None,
        description="Optional deployment profile for env/image/runtime overrides.",
    )
    topology_version_id: UUID | None = Field(
        default=None,
        description="Optional topology version snapshot to deploy (defaults to current).",
    )
