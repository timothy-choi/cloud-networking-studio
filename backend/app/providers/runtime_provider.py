"""Abstract runtime provider — swap implementations (Docker, K8s, OpenStack, …)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.models.deployment import DeploymentEventLevel
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
