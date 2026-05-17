"""Docker runtime with deploy/destroy/logs/traffic delegated to the Go runner when enabled."""

from __future__ import annotations

import logging
from uuid import UUID

from app.models.deployment import DeploymentEventLevel
from app.providers.docker_runtime_provider import DockerRuntimeProvider
from app.providers.runtime_provider import ProviderEvent, RuntimeProvider
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


class GoHybridDockerRuntimeProvider(RuntimeProvider):
    """
    Executes mutating Docker work via the Go runner; inspect/exec/stats still use docker-py.

    This keeps API behaviour aligned with the Python provider while the Go surface grows
    (e.g. future Kubernetes backends).
    """

    def __init__(self, docker: DockerRuntimeProvider, runner: GoRunnerClient) -> None:
        self._docker = docker
        self._runner = runner

    def deploy(self, plan: DeploymentPlan) -> list[ProviderEvent]:
        _log.info("runtime_executor=go delegating deploy to Go runner")
        return self._runner.post_deployment(plan)

    def destroy(self, topology_id: UUID, deployment_id: UUID) -> list[ProviderEvent]:
        _log.info("runtime_executor=go delegating destroy to Go runner")
        return self._runner.delete_deployment(deployment_id, topology_id)

    def inspect_topology_runtime(self, topology_id: UUID) -> ProviderRuntimeSnapshot:
        return self._docker.inspect_topology_runtime(topology_id)

    def fetch_logs_for_node(
        self,
        topology_id: UUID,
        node_id: UUID,
        tail: int,
        *,
        deployment_id: UUID | None = None,
    ) -> str | None:
        if deployment_id is not None:
            text = self._runner.get_deployment_logs(deployment_id, topology_id, node_id, tail)
            if text is not None:
                return text
        return self._docker.fetch_logs_for_node(
            topology_id, node_id, tail, deployment_id=deployment_id
        )

    def fetch_stats_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> ProviderRuntimeStats | None:
        return self._docker.fetch_stats_for_node(topology_id, node_id)

    def reconcile_runtime(
        self,
        topology_id: UUID,
        desired_node_ids: frozenset[UUID],
    ) -> ProviderReconciliationResult:
        return self._docker.reconcile_runtime(topology_id, desired_node_ids)

    def heal_restart_stopped(self, topology_id: UUID) -> ProviderHealingResult:
        return self._docker.heal_restart_stopped(topology_id)

    def find_container_id_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> str | None:
        return self._docker.find_container_id_for_node(topology_id, node_id)

    def exec_in_node_container(
        self,
        topology_id: UUID,
        node_id: UUID,
        argv: list[str],
    ) -> ProviderExecResult | None:
        return self._docker.exec_in_node_container(topology_id, node_id, argv)

    def resolve_node_ipv4(
        self,
        topology_id: UUID,
        node_id: UUID,
        source_node_id: UUID | None = None,
    ) -> str | None:
        return self._docker.resolve_node_ipv4(topology_id, node_id, source_node_id)

    def stop_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        self._docker.stop_node_container(topology_id, node_id)

    def restart_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        self._docker.restart_node_container(topology_id, node_id)

    def kill_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        self._docker.kill_node_container(topology_id, node_id)
