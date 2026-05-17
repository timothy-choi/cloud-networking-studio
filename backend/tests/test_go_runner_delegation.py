"""Tests that RUNTIME_EXECUTOR=go wires deploy/destroy to GoRunnerClient."""

from __future__ import annotations

import uuid

import pytest

from app.core import config
from app.models.deployment import DeploymentEventLevel
from app.providers.docker_runtime_provider import runtime_provider_for_topology
from app.providers.go_hybrid_runtime_provider import GoHybridDockerRuntimeProvider
from app.runtime import go_runner_client as grc
from app.services.deployment_planner import (
    DeploymentPlan,
    PlanLinkDetail,
    PlanNode,
)


def _minimal_plan() -> DeploymentPlan:
    tid = uuid.uuid4()
    nid = uuid.uuid4()
    lid = uuid.uuid4()
    did = uuid.uuid4()
    node = PlanNode(
        id=nid,
        name="n1",
        image="alpine:latest",
        ip_address="10.0.0.2",
        node_type="host",
    )
    pl = PlanLinkDetail(
        link_id=lid,
        source_node_id=nid,
        target_node_id=nid,
        source_name="n1",
        target_name="n1",
        network_name="net0",
        cidr="10.0.0.0/24",
        gateway=None,
        vlan_tag=None,
        source_ip="10.0.0.2",
        target_ip="10.0.0.3",
    )
    return DeploymentPlan(
        topology_id=tid,
        runtime_target="docker",
        networking_mode="docker_bridge",
        steps=("validate_topology",),
        nodes=(node,),
        node_names=("n1",),
        links=(("n1", "n1", "net0"),),
        plan_links=(pl,),
        segmented_networks=False,
        subnet_cidr="10.0.0.0/24",
        deployment_id=did,
        project_id=None,
        requested_by_user_id=None,
    )


@pytest.fixture
def go_executor_no_fake_docker(monkeypatch):
    monkeypatch.delenv("CNS_USE_FAKE_DOCKER", raising=False)
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")


def test_effective_runtime_executor_prefers_process_environ(monkeypatch):
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "python")
    assert grc.effective_runtime_executor() == "go"


def test_go_executor_uses_hybrid_provider(go_executor_no_fake_docker):
    prov = runtime_provider_for_topology("docker")
    assert isinstance(prov, GoHybridDockerRuntimeProvider)


def test_go_executor_deploy_calls_runner_client(go_executor_no_fake_docker, monkeypatch):
    calls: list[str] = []

    def capture_post(self, plan: DeploymentPlan):
        calls.append("post_deployment")
        return [(DeploymentEventLevel.INFO, "stubbed runner deploy")]

    monkeypatch.setattr(grc.GoRunnerClient, "post_deployment", capture_post)
    prov = runtime_provider_for_topology("docker")
    assert isinstance(prov, GoHybridDockerRuntimeProvider)
    events = prov.deploy(_minimal_plan())
    assert calls == ["post_deployment"]
    assert events[0][1] == "stubbed runner deploy"


def test_go_executor_destroy_calls_runner_client(go_executor_no_fake_docker, monkeypatch):
    calls: list[str] = []

    def capture_delete(self, deployment_id, topology_id):
        calls.append("delete_deployment")
        return [(DeploymentEventLevel.INFO, "stubbed runner destroy")]

    monkeypatch.setattr(grc.GoRunnerClient, "delete_deployment", capture_delete)
    prov = runtime_provider_for_topology("docker")
    assert isinstance(prov, GoHybridDockerRuntimeProvider)
    tid = uuid.uuid4()
    did = uuid.uuid4()
    events = prov.destroy(tid, did)
    assert calls == ["delete_deployment"]
    assert events[0][1] == "stubbed runner destroy"


def test_python_executor_does_not_use_hybrid_when_fake_docker(monkeypatch):
    monkeypatch.setenv("CNS_USE_FAKE_DOCKER", "1")
    monkeypatch.setenv("RUNTIME_EXECUTOR", "python")
    monkeypatch.setattr(config.settings, "runtime_executor", "python")
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    prov = runtime_provider_for_topology("docker")
    assert isinstance(prov, FakeDockerRuntimeProvider)

    calls: list[str] = []

    def capture_post(self, plan):
        calls.append("should_not_run")
        return []

    monkeypatch.setattr(grc.GoRunnerClient, "post_deployment", capture_post)
    prov.deploy(_minimal_plan())
    assert calls == []
