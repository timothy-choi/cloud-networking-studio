"""Unit tests for the optional Go runner HTTP client."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core import config
from app.models.deployment import DeploymentEventLevel
from app.runtime.go_runner_client import GoRunnerClient, GoRunnerDeployError, use_go_runner_for_docker
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
    pid = uuid.uuid4()
    uid = uuid.uuid4()
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
        project_id=pid,
        requested_by_user_id=uid,
    )


def test_deployment_plan_to_runner_payload_includes_ids():
    plan = _minimal_plan()
    c = GoRunnerClient("http://runner:8090", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    body = c.deployment_request_body(plan)
    assert body["deployment_id"] == str(plan.deployment_id)
    assert body["topology_id"] == str(plan.topology_id)
    assert body["project_id"] == str(plan.project_id)
    assert body["requested_by_user_id"] == str(plan.requested_by_user_id)
    assert body["segmented_networks"] is False
    assert len(body["nodes"]) == 1
    assert len(body["plan_links"]) == 1


def test_post_deployment_success_maps_events():
    plan = _minimal_plan()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/deployments"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "runtime_provider": "docker",
                "events": [{"level": "info", "message": "from runner"}],
            },
        )

    c = GoRunnerClient("http://runner:8090", transport=httpx.MockTransport(handler))
    rows = c.post_deployment(plan)
    assert rows == [(DeploymentEventLevel.INFO, "from runner")]


def test_post_deployment_failure_raises_with_events():
    plan = _minimal_plan()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status": "failed",
                "runtime_provider": "docker",
                "events": [{"level": "warning", "message": "w1"}],
                "error": "boom",
            },
        )

    c = GoRunnerClient("http://runner:8090", transport=httpx.MockTransport(handler))
    with pytest.raises(GoRunnerDeployError) as ei:
        c.post_deployment(plan)
    assert ei.value.message == "boom"
    assert ei.value.events == [(DeploymentEventLevel.WARNING, "w1")]


def test_use_go_runner_false_under_fake_docker(monkeypatch):
    monkeypatch.setenv("CNS_USE_FAKE_DOCKER", "1")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")
    assert use_go_runner_for_docker() is False


def test_use_go_runner_true_when_executor_go(monkeypatch):
    monkeypatch.delenv("CNS_USE_FAKE_DOCKER", raising=False)
    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")
    assert use_go_runner_for_docker() is True
