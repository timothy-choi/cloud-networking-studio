"""Kubernetes runtime with deploy/destroy/logs delegated to the Go runner."""

from __future__ import annotations

import logging
from uuid import UUID

from app.models.deployment import DeploymentEventLevel
from app.providers.runtime_provider import DeployOutcome, ProviderEvent, RuntimeProvider
from app.providers.runtime_types import (
    ProviderExecResult,
    ProviderHealingResult,
    ProviderReconciliationResult,
    ProviderRuntimeSnapshot,
    ProviderRuntimeStats,
)
from app.runtime.go_runner_client import GoRunnerClient
from app.services.deployment_planner import DeploymentPlan

_log = logging.getLogger(__name__)


class GoHybridKubernetesRuntimeProvider(RuntimeProvider):
    """
    Executes mutating Kubernetes work via the Go runner.

    Read-only inspect/reconcile/stats remain unavailable until a Kubernetes
    inspection path is implemented in the control plane.
    """

    def __init__(self, runner: GoRunnerClient) -> None:
        self._runner = runner

    def deploy(self, plan: DeploymentPlan) -> DeployOutcome:
        _log.info("runtime_executor=go delegating kubernetes deploy to Go runner")
        events, ra = self._runner.post_deployment(plan)
        return DeployOutcome(events=events, runtime_access=ra)

    def destroy(
        self,
        topology_id: UUID,
        deployment_id: UUID,
        *,
        project_id: UUID | None = None,
    ) -> list[ProviderEvent]:
        _log.info("runtime_executor=go delegating kubernetes destroy to Go runner")
        return self._runner.delete_deployment(
            deployment_id, topology_id, project_id=project_id
        )

    def inspect_topology_runtime(self, topology_id: UUID) -> ProviderRuntimeSnapshot:
        return ProviderRuntimeSnapshot(networks=[], containers=[])

    def fetch_logs_for_node(
        self,
        topology_id: UUID,
        node_id: UUID,
        tail: int,
        *,
        deployment_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str | None:
        if deployment_id is not None:
            return self._runner.get_deployment_logs(
                deployment_id,
                topology_id,
                node_id,
                tail,
                project_id=project_id,
            )
        return None

    def fetch_stats_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> ProviderRuntimeStats | None:
        return None

    def reconcile_runtime(
        self,
        topology_id: UUID,
        desired_node_ids: frozenset[UUID],
    ) -> ProviderReconciliationResult:
        return ProviderReconciliationResult(
            missing_network=False,
            missing_node_ids=[],
            stopped_containers=[],
            summary_lines=["Kubernetes reconcile is not implemented in the control plane yet."],
        )

    def heal_restart_stopped(self, topology_id: UUID) -> ProviderHealingResult:
        return ProviderHealingResult(restarted=[], errors=[])

    def find_container_id_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> str | None:
        return None

    def exec_in_node_container(
        self,
        topology_id: UUID,
        node_id: UUID,
        argv: list[str],
    ) -> ProviderExecResult | None:
        return None

    def resolve_node_ipv4(
        self,
        topology_id: UUID,
        node_id: UUID,
        source_node_id: UUID | None = None,
    ) -> str | None:
        return None

    def stop_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        raise NotImplementedError("Kubernetes stop is not supported via docker-py hybrid path")

    def restart_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        raise NotImplementedError("Use runtime restart via Go runner for Kubernetes workloads")

    def kill_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        raise NotImplementedError("Kubernetes kill is not supported via docker-py hybrid path")
