"""Abstract runtime provider — swap implementations (Docker, K8s, OpenStack, …)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.models.deployment import DeploymentEventLevel
from app.providers.runtime_types import (
    ProviderExecResult,
    ProviderHealingResult,
    ProviderReconciliationResult,
    ProviderRuntimeSnapshot,
    ProviderRuntimeStats,
)
from app.services.deployment_planner import DeploymentPlan

ProviderEvent = tuple[DeploymentEventLevel, str]


class RuntimeProvider(ABC):
    """Execute a deployment plan against a concrete infrastructure backend."""

    @abstractmethod
    def deploy(self, plan: DeploymentPlan) -> list[ProviderEvent]:
        """
        Run (or simulate) deployment steps.

        Returns (level, message) rows stored as deployment events.
        """

    @abstractmethod
    def destroy(self, topology_id: UUID, deployment_id: UUID) -> list[ProviderEvent]:
        """Tear down external resources created for this topology/deployment."""

    @abstractmethod
    def inspect_topology_runtime(self, topology_id: UUID) -> ProviderRuntimeSnapshot:
        """Observe networks + containers for ``topology_id`` (labels, not hardcoded names)."""

    @abstractmethod
    def fetch_logs_for_node(
        self, topology_id: UUID, node_id: UUID, tail: int
    ) -> str | None:
        """Return recent container stdout/stderr, or None if no matching container."""

    @abstractmethod
    def fetch_stats_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> ProviderRuntimeStats | None:
        """Lightweight resource stats, or None if no matching / stats unavailable."""

    @abstractmethod
    def reconcile_runtime(
        self,
        topology_id: UUID,
        desired_node_ids: frozenset[UUID],
    ) -> ProviderReconciliationResult:
        """Compare desired node set vs actual containers/networks; report drift only."""

    @abstractmethod
    def heal_restart_stopped(self, topology_id: UUID) -> ProviderHealingResult:
        """Restart managed containers that exist but are not running (provider-specific)."""

    @abstractmethod
    def find_container_id_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> str | None:
        """Runtime container id for the managed node, if present."""

    @abstractmethod
    def exec_in_node_container(
        self,
        topology_id: UUID,
        node_id: UUID,
        argv: list[str],
    ) -> ProviderExecResult | None:
        """Run argv inside the node's container; None if container not found."""

    @abstractmethod
    def resolve_node_ipv4(
        self,
        topology_id: UUID,
        node_id: UUID,
        source_node_id: UUID | None = None,
    ) -> str | None:
        """IPv4 for traffic tests; ``source_node_id`` disambiguates multi-homed / routed targets."""

    @abstractmethod
    def stop_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        """Stop the runtime workload for ``node_id`` (Docker stop / equivalent)."""

    @abstractmethod
    def restart_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        """Restart the runtime workload for ``node_id``."""

    @abstractmethod
    def kill_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        """Force-stop the runtime workload for ``node_id`` (SIGKILL / equivalent)."""
