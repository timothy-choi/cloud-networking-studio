"""Simulated Docker runtime — no Docker socket calls; emits timeline-style messages."""

from __future__ import annotations

from app.providers.runtime_provider import RuntimeProvider
from app.services.deployment_planner import DeploymentPlan


class FakeDockerRuntimeProvider(RuntimeProvider):
    """Placeholder Docker backend for vertical-slice testing and demos."""

    def deploy(self, plan: DeploymentPlan) -> list[str]:
        messages: list[str] = [
            "Deployment plan validated",
            f"Runtime provider selected: {plan.runtime_target}",
            "Virtual network creation scheduled",
        ]
        for name in plan.node_names:
            messages.append(f"Node container creation scheduled: {name}")
        for src, tgt, net in plan.links:
            messages.append(f"Link scheduled: {src} -> {tgt} ({net})")
        messages.extend(
            [
                "Health checks scheduled",
                "Deployment simulation completed",
            ]
        )
        return messages
