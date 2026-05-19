"""Deploy request bodies."""

from pydantic import BaseModel, Field

from app.services.network_allocation import DEFAULT_NETWORK_ALLOCATION_MODE


class TopologyDeployRequest(BaseModel):
    """Optional deploy overrides (defaults come from topology.config)."""

    network_allocation_mode: str | None = Field(
        default=None,
        description="`managed` (Docker assigns runtime IPs) or `intent` (honor static topology IPs).",
        examples=[DEFAULT_NETWORK_ALLOCATION_MODE, "intent"],
    )
