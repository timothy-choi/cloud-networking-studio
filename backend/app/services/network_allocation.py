"""Network allocation mode: managed (Docker assigns IPs) vs intent (static topology IPs)."""

from __future__ import annotations

from typing import Any

from app.models.topology import Topology

MANAGED = "managed"
INTENT = "intent"
DEFAULT_NETWORK_ALLOCATION_MODE = MANAGED

INTENT_SUBNET_OVERLAP_USER_MESSAGE = (
    "Requested topology subnet overlaps with existing Docker network. "
    "Use managed mode or choose a different subnet."
)

INTENT_UNSUPPORTED_RUNTIME_MESSAGE = (
    "Intent IP preservation is currently supported for Docker runtime only."
)

CONFIG_KEY = "network_allocation_mode"


def normalize_network_allocation_mode(raw: str | None) -> str:
    """Return ``managed`` or ``intent``; unknown values map to managed."""
    if raw is None:
        return DEFAULT_NETWORK_ALLOCATION_MODE
    v = str(raw).strip().lower()
    if v in (INTENT, "intent_ips", "static"):
        return INTENT
    return MANAGED


def is_intent_mode(mode: str | None) -> bool:
    return normalize_network_allocation_mode(mode) == INTENT


def read_mode_from_topology_config(config: dict[str, Any] | None) -> str:
    if not config or not isinstance(config, dict):
        return DEFAULT_NETWORK_ALLOCATION_MODE
    raw = config.get(CONFIG_KEY)
    return normalize_network_allocation_mode(str(raw) if raw is not None else None)


def resolve_network_allocation_mode(
    topology: Topology,
    override: str | None = None,
) -> str:
    """Precedence: deploy request override → topology.config → managed."""
    if override is not None and str(override).strip():
        return normalize_network_allocation_mode(override)
    return read_mode_from_topology_config(topology.config)


def merge_allocation_mode_into_config(
    config: dict[str, Any] | None,
    mode: str,
) -> dict[str, Any]:
    """Persist mode on topology.config (shallow copy)."""
    out: dict[str, Any] = dict(config) if config and isinstance(config, dict) else {}
    out[CONFIG_KEY] = normalize_network_allocation_mode(mode)
    return out
