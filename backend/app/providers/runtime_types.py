"""Structured runtime inspection payloads — provider-neutral dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RuntimeNetworkRecord:
    """One Docker (or future) network attachment to the topology."""

    network_id: str
    name: str
    driver: str
    labels: dict[str, str]
    scope: str | None = None
    ipam_driver: str | None = None
    subnet_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeContainerRecord:
    """Materialized node container as observed at runtime."""

    container_id: str
    short_id: str
    name: str
    image: str
    status: str
    state_status: str | None
    running: bool
    labels: dict[str, str]
    node_id: UUID | None
    ipv4_by_network: dict[str, str]
    created: str | None
    started_at: str | None


@dataclass(frozen=True)
class ProviderRuntimeSnapshot:
    """Live topology slice returned by a runtime provider."""

    networks: tuple[RuntimeNetworkRecord, ...] = ()
    containers: tuple[RuntimeContainerRecord, ...] = ()


@dataclass(frozen=True)
class ProviderReconciliationResult:
    """Drift between desired topology nodes and observed Docker state."""

    missing_network: bool
    missing_node_ids: tuple[UUID, ...] = ()
    stopped_containers: tuple[tuple[str, str], ...] = ()
    """(container_id, human_readable_name)."""
    summary_lines: tuple[str, ...] = ()


@dataclass
class ProviderRuntimeStats:
    """Lightweight container resource usage."""

    cpu_percent: float | None = None
    memory_usage_bytes: int | None = None
    memory_limit_bytes: int | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None
