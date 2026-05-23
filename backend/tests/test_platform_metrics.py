"""Platform observability metrics (Step 53C)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType

TOPOLOGY_BODY = {
    "name": "Metrics Lab",
    "description": "metrics test",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_with_node(client, headers: dict | None = None) -> str:
    h = headers or {}
    r = client.post("/topologies", json=TOPOLOGY_BODY, headers=h)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "host-a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
        headers=h,
    )
    return tid


def _register(client_strict, prefix: str = "m") -> tuple[dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "M"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    return h, pid


def test_platform_metrics_returns_expected_shape(client):
    r = client.get("/platform/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "platform"
    for key in (
        "active_deployments",
        "deployment_success_count",
        "deployment_failure_count",
        "deploy_duration",
        "active_terminal_sessions",
        "runtime_provider_status",
        "quota_usage",
        "recent_failed_operations",
        "cleanup_status",
        "api_requests",
    ):
        assert key in body
    assert isinstance(body["active_deployments"], int)
    assert body["active_deployments"] >= 0
    assert "average_deploy_duration_seconds" in body["deploy_duration"]
    assert "sample_count" in body["deploy_duration"]
    runtime = body["runtime_provider_status"]
    assert "status" in runtime
    assert "runtime_executor" in runtime
    quota = body["quota_usage"]
    assert "limits" in quota
    assert isinstance(quota["limits"], dict)
    cleanup = body["cleanup_status"]
    for key in ("eligible_deployments", "deployments_with_runtime_resources", "stale_terminal_sessions"):
        assert key in cleanup
        assert isinstance(cleanup[key], int)
    api = body["api_requests"]
    assert "total_requests" in api
    assert "by_status" in api
    assert isinstance(api["by_status"], dict)


def test_project_metrics_returns_expected_shape(client):
    tid = _topology_with_node(client)
    topo = client.get(f"/topologies/{tid}").json()
    pid = topo["project_id"]
    r = client.get(f"/projects/{pid}/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "project"
    assert body["project_id"] == pid
    for key in (
        "active_deployments",
        "deployment_success_count",
        "deployment_failure_count",
        "deploy_duration",
        "active_terminal_sessions",
        "quota_usage",
        "recent_failed_operations",
        "cleanup_status",
    ):
        assert key in body


def test_deployment_metrics_returns_expected_shape(client):
    tid = _topology_with_node(client)
    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201, d.text
    did = d.json()["id"]
    r = client.get(f"/deployments/{did}/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "deployment"
    assert body["deployment_id"] == did
    assert body["topology_id"] == tid
    for key in (
        "status",
        "deploy_duration_seconds",
        "runtime_resources_count",
        "active_terminal_sessions",
        "cleanup_status",
        "recent_failed_operations",
    ):
        assert key in body


def test_project_metrics_blocks_non_members(client_strict):
    ha, pid = _register(client_strict, "ma")
    hb, _ = _register(client_strict, "mb")
    assert client_strict.get(f"/projects/{pid}/metrics", headers=ha).status_code == 200
    assert client_strict.get(f"/projects/{pid}/metrics", headers=hb).status_code == 404


def test_deployment_metrics_blocks_non_members(client_strict):
    ha, _ = _register(client_strict, "da")
    tid = _topology_with_node(client_strict, ha)
    d = client_strict.post(f"/topologies/{tid}/deploy", headers=ha)
    assert d.status_code == 201, d.text
    did = d.json()["id"]
    hb, _ = _register(client_strict, "db")
    assert client_strict.get(f"/deployments/{did}/metrics", headers=ha).status_code == 200
    assert client_strict.get(f"/deployments/{did}/metrics", headers=hb).status_code == 404


def test_metrics_summary_still_works(client):
    r = client.get("/metrics/summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_deployments" in body
    assert "latest_events" in body
