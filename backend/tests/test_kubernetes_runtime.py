"""Kubernetes runtime hardening tests."""

from __future__ import annotations

from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.providers.go_hybrid_kubernetes_runtime_provider import GoHybridKubernetesRuntimeProvider
from app.providers.go_hybrid_runtime_provider import GoHybridDockerRuntimeProvider
from app.runtime.go_runner_client import effective_runtime_executor
from app.services.node_runtime_config import extract_node_runtime_config


def test_docker_provider_still_hybrid_when_executor_go(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.delenv("CNS_USE_FAKE_DOCKER", raising=False)
    monkeypatch.setattr(
        "app.providers.docker_runtime_provider.DockerRuntimeProvider",
        lambda *args, **kwargs: object(),
    )
    prov = runtime_provider_for_topology("docker")
    assert isinstance(prov, GoHybridDockerRuntimeProvider)


def test_kubernetes_provider_uses_go_hybrid_when_executor_go(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.delenv("CNS_USE_FAKE_DOCKER", raising=False)
    prov = runtime_provider_for_topology("kubernetes")
    assert isinstance(prov, GoHybridKubernetesRuntimeProvider)


def test_kubernetes_provider_fake_when_executor_python(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "python")
    monkeypatch.delenv("CNS_USE_FAKE_DOCKER", raising=False)
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    prov = runtime_provider_for_topology("kubernetes")
    assert isinstance(prov, FakeDockerRuntimeProvider)


def test_runtime_status_degraded_when_runner_unreachable(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    import httpx

    def _boom(self):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.get_runtime_status",
        _boom,
    )
    from app.api.runtime import get_runtime_executor_status

    body = get_runtime_executor_status()
    assert body["status"] == "degraded"
    assert body.get("runner_reachable") is False
    assert body.get("message")


def test_kubernetes_service_type_extracted_from_node_config():
    runtime = extract_node_runtime_config(
        {"kubernetes_service_type": "NodePort", "command": "sleep infinity"}
    )
    assert runtime.kubernetes_service_type == "NodePort"


def test_effective_runtime_executor_defaults():
    assert effective_runtime_executor() in ("go", "python")
