"""Abstract runtime provider — swap implementations (Docker, K8s, OpenStack, …)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.deployment_planner import DeploymentPlan


class RuntimeProvider(ABC):
    """Execute a deployment plan against a concrete infrastructure backend."""

    @abstractmethod
    def deploy(self, plan: DeploymentPlan) -> list[str]:
        """
        Run (or simulate) deployment steps.

        Returns human-readable log lines stored as deployment events.
        """
