"""Tests for structured runner runtime error tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.runtime.runner_operation_history import list_recent_runner_operations
from app.runtime.runner_runtime_error import (
    clear_runtime_error,
    get_runtime_error,
    set_runtime_error,
)


def test_stale_status_error_not_active(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    clear_runtime_error()
    set_runtime_error(
        operation="runtime_status",
        message="probe failed",
        status_code=503,
        timestamp=datetime.now(UTC) - timedelta(minutes=10),
    )

    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_get_runtime_status(_self):
        return {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", fake_get_runtime_status)
    monkeypatch.setattr(
        grc.GoRunnerClient,
        "get_runner_status",
        lambda _self: {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        },
    )

    r = client.get("/runtime/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("last_runtime_error") is None

    r2 = client.get("/runtime/runner-status")
    assert r2.status_code == 200
    assert r2.json().get("last_runtime_error") is None
    clear_runtime_error()


def test_successful_status_check_clears_probe_error(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    clear_runtime_error()
    set_runtime_error(
        operation="runner_status",
        message="Go runner unavailable",
        status_code=503,
    )

    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_get_runtime_status(_self):
        return {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        }

    def fake_get_runner_status(_self):
        return {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", fake_get_runtime_status)
    monkeypatch.setattr(grc.GoRunnerClient, "get_runner_status", fake_get_runner_status)

    r = client.post("/runtime/runner-recheck")
    assert r.status_code == 200
    body = r.json()
    assert body.get("last_runtime_error") is None
    assert get_runtime_error(include_historical=True) is None


def test_deploy_failure_remains_until_deploy_succeeds(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc
    from app.runtime.runner_operation_history import record_runner_operation

    clear_runtime_error()
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    set_runtime_error(
        operation="deploy",
        message="invalid topology",
        status_code=400,
        request_id="req-deploy-fail",
    )
    record_runner_operation(
        operation="deploy",
        provider="docker",
        status="error",
        duration_ms=25,
        request_id="req-deploy-fail",
        error_message="invalid topology",
        status_code=400,
    )

    def fake_get_runtime_status(_self):
        return {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", fake_get_runtime_status)
    monkeypatch.setattr(
        grc.GoRunnerClient,
        "get_runner_status",
        lambda _self: {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
        },
    )

    r = client.get("/runtime/status")
    err = r.json().get("last_runtime_error")
    assert err is not None
    assert err["operation"] == "deploy"
    assert err["status_code"] == 400
    assert err["message"] == "invalid topology"
    assert err["request_id"] == "req-deploy-fail"
    assert err.get("historical") is False


def test_failed_runner_call_appears_in_recent_operations():
    from app.runtime.runner_operation_history import record_runner_operation

    record_runner_operation(
        operation="deploy",
        provider="docker",
        status="error",
        duration_ms=33,
        request_id="req-fail-1",
        error_message="invalid topology",
        status_code=400,
    )
    rows = list_recent_runner_operations(limit=5)
    failed = [r for r in rows if r["operation"] == "deploy" and r["status"] == "error"]
    assert failed
    assert failed[0]["status_code"] == 400
    assert failed[0]["error_message"] == "invalid topology"


def test_go_runner_client_structured_deploy_error():
    import uuid

    from app.runtime.go_runner_client import GoRunnerClient, GoRunnerDeployError
    from app.services.deployment_planner import DeploymentPlan, PlanLinkDetail, PlanNode

    clear_runtime_error()
    tid = uuid.uuid4()
    nid = uuid.uuid4()
    plan = DeploymentPlan(
        topology_id=tid,
        runtime_target="docker",
        networking_mode="docker_bridge",
        steps=("validate_topology",),
        nodes=(
            PlanNode(
                id=nid,
                name="n1",
                image="alpine:latest",
                ip_address="10.0.0.2",
                node_type="host",
            ),
        ),
        node_names=("n1",),
        links=(),
        plan_links=(
            PlanLinkDetail(
                link_id=uuid.uuid4(),
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
            ),
        ),
        segmented_networks=False,
        subnet_cidr="10.0.0.0/24",
        deployment_id=uuid.uuid4(),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status": "failed",
                "runtime_provider": "docker",
                "events": [],
                "error": "topology has no links",
            },
        )

    client = GoRunnerClient("http://runner:8090", transport=httpx.MockTransport(handler))
    with pytest.raises(GoRunnerDeployError):
        client.post_deployment(plan)

    err = get_runtime_error(include_historical=False)
    assert err is not None
    assert err["operation"] == "deploy"
    assert err["status_code"] == 400
    assert "topology has no links" in err["message"]
    clear_runtime_error()
