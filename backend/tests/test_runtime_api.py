"""Runtime API integration tests (fake Docker provider — no engine required)."""

from __future__ import annotations

import uuid

import httpx

from app.models.topology import NodeType


def test_topology_runtime_returns_payload_after_deploy(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Obs Lab",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201
    did = d.json()["id"]

    rt = client.get(f"/topologies/{tid}/runtime")
    assert rt.status_code == 200
    body = rt.json()
    assert body["topology_id"] == tid
    assert body["deployment_status"] == "succeeded"
    assert body["latest_deployment_id"] == did
    assert body["networks"] == []
    assert body["containers"] == []
    assert body["runtime_provider"] == "docker"

    ev = client.get(f"/deployments/{did}/events").json()
    assert any("Runtime inspection" in e["message"] for e in ev)

    dr = client.get(f"/deployments/{did}/runtime")
    assert dr.status_code == 200
    dre = dr.json()
    assert dre["deployment_id"] == did
    assert dre["topology_id"] == tid
    assert dre.get("instructions") is not None
    assert "local_dev" in dre["instructions"]
    assert dre["instructions"]["app_env"]["title"] == "Use from app"


def test_deployment_reconcile_reports_drift_with_fake_provider(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Reconcile Lab",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na,
            "target_node_id": nb,
            "network_name": "lab-net",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy").json()
    did = dep["id"]

    rec = client.post(f"/deployments/{did}/reconcile")
    assert rec.status_code == 200
    payload = rec.json()
    assert payload["missing_network"] is True
    assert uuid.UUID(na) in [uuid.UUID(x) for x in payload["missing_node_ids"]]
    assert uuid.UUID(nb) in [uuid.UUID(x) for x in payload["missing_node_ids"]]

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Runtime reconciliation started" in m for m in msgs)
    assert any("Missing resource detected" in m for m in msgs)
    assert any("Runtime reconciliation completed" in m for m in msgs)


def test_node_logs_404_without_runtime_container(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Logs",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "solo",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nid = n["id"]
    lg = client.get(f"/nodes/{nid}/logs")
    assert lg.status_code == 404


def test_runtime_topology_unknown_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/topologies/{missing}/runtime").status_code == 404


def test_runtime_deployment_unknown_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/deployments/{missing}/runtime").status_code == 404


def test_deployment_runtime_instructions_shape_after_deploy(client):
    r = client.post(
        "/topologies",
        json={
            "name": "Runtime access lab",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]

    full = client.get(f"/deployments/{did}/runtime").json()
    inst = full["instructions"]
    for key in ("local_dev", "app_env", "ci_cd", "kubernetes", "api"):
        assert key in inst
    assert inst["local_dev"]["title"] == "Connect from local machine"
    assert inst["app_env"]["title"] == "Use from app"
    assert inst["ci_cd"]["title"] == "Use in CI/CD"
    assert inst["kubernetes"]["title"] == "Use from Kubernetes workload"
    assert inst["api"]["title"] == "Control through API"

    nodes_sec = client.get(f"/deployments/{did}/runtime/nodes").json()
    assert nodes_sec["deployment_id"] == did
    assert nodes_sec["nodes"] == []

    svc_sec = client.get(f"/deployments/{did}/runtime/services").json()
    assert svc_sec["deployment_id"] == did
    assert svc_sec["services"] == []

    inst_only = client.get(f"/deployments/{did}/runtime/instructions").json()
    assert inst_only["deployment_id"] == did
    assert set(inst_only["instructions"].keys()) >= {
        "local_dev",
        "app_env",
        "ci_cd",
        "kubernetes",
        "api",
    }

    logs = client.get(f"/deployments/{did}/runtime/logs").json()
    assert logs["deployment_id"] == did
    assert logs["runtime_provider"] == "docker"
    assert isinstance(logs["items"], list)
    assert len(logs["items"]) >= 1


def test_deployment_runtime_returns_persisted_resources(client):
    from uuid import UUID

    from app.db.session import SessionLocal
    from app.services.deployment_runtime_resource_service import (
        replace_runtime_resources_from_payload,
    )

    r = client.post(
        "/topologies",
        json={
            "name": "Persisted runtime",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    )
    tid = r.json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "api-service",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nid = n["id"]
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]

    with SessionLocal() as db:
        replace_runtime_resources_from_payload(
            db,
            UUID(did),
            {
                "runtime_provider": "kubernetes",
                "namespace_or_network": "cns-p-demo-d-abc",
                "resources": [
                    {
                        "type": "node",
                        "node_id": nid,
                        "name": "api-service",
                        "runtime_name": "cns-node-api-service-xyz",
                        "status": "running",
                        "namespace_or_network": "cns-p-demo-d-abc",
                    },
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "api-service",
                        "runtime_name": "cns-node-api-service-svc",
                        "status": "running",
                        "namespace_or_network": "cns-p-demo-d-abc",
                        "ports": [{"port": 80, "target_port": 8080, "protocol": "TCP"}],
                        "internal_url": "http://cns-node-api-service-svc.cns-p-demo-d-abc.svc.cluster.local:80",
                    },
                ],
            },
        )
        db.commit()

    dr = client.get(f"/deployments/{did}/runtime").json()
    assert dr["namespace_or_network"] == "cns-p-demo-d-abc"
    assert len(dr["nodes"]) == 1
    assert dr["nodes"][0]["runtime_name"] == "cns-node-api-service-xyz"
    assert len(dr["services"]) == 1
    assert "svc.cluster.local" in dr["services"][0]["internal_url"]
    assert len(dr["endpoints"]) >= 1

    dr_api = client.get(f"/api/deployments/{did}/runtime").json()
    assert dr_api["deployment_id"] == did
    assert dr_api["namespace_or_network"] == dr["namespace_or_network"]
    assert dr_api["nodes"] == dr["nodes"]
    assert dr_api["services"] == dr["services"]

    assert client.get(f"/api/deployments/{did}/runtime/nodes").status_code == 200
    assert client.get(f"/api/deployments/{did}/runtime/services").status_code == 200
    assert client.get(f"/api/deployments/{did}/runtime/instructions").status_code == 200
    assert client.get(f"/api/deployments/{did}/runtime/logs").status_code == 200

    logs2 = client.get(f"/deployments/{did}/runtime/logs").json()
    assert len(logs2["items"]) == 1
    assert logs2["items"][0]["node_id"] == nid


def test_public_runtime_status_python_executor(client):
    r = client.get("/runtime/status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("backend_status") == "ok"
    assert data.get("runtime_executor") == "python"
    assert data.get("runtime_provider") == "python"
    assert "docker_reachable" in data


def test_health_accepts_optional_api_prefix(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_deployment_runtime_get_routes_registered_under_deployments_tag():
    from fastapi.routing import APIRoute

    from app.main import app

    get_want = {
        "/deployments/{deployment_id}/runtime",
        "/deployments/{deployment_id}/runtime/logs",
        "/deployments/{deployment_id}/runtime/nodes",
        "/deployments/{deployment_id}/runtime/services",
        "/deployments/{deployment_id}/runtime/services/{service_id}/logs",
        "/deployments/{deployment_id}/runtime/instructions",
    }
    post_want = {
        "/deployments/{deployment_id}/runtime/services/{service_id}/health-check",
        "/deployments/{deployment_id}/runtime/traffic-tests",
        "/deployments/{deployment_id}/runtime/cleanup",
    }
    found_get: set[str] = set()
    found_post: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or "deployments" not in route.tags:
            continue
        if route.path in get_want and "GET" in route.methods:
            found_get.add(route.path)
        if route.path in post_want and "POST" in route.methods:
            found_post.add(route.path)
    assert found_get == get_want
    assert found_post == post_want


def test_get_runtime_status_route_registered_on_app():
    from app.main import app

    found = False
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path == "/runtime/status" and "GET" in methods:
            found = True
            break
    assert found, "GET /runtime/status must be registered on the FastAPI app"


def test_public_runtime_status_go_proxies_runner(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_get_runtime_status(self):
        return {
            "status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
            "message": "",
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", fake_get_runtime_status)
    r = client.get("/runtime/status")
    assert r.status_code == 200
    body = r.json()
    assert body["runtime_provider"] == "docker"
    assert body["docker_reachable"] is True
    assert body.get("runner_reachable") is True
    assert body.get("backend_status") == "ok"


def test_public_runtime_status_go_runner_unavailable_returns_degraded(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def boom(self):
        raise httpx.ConnectError(
            "refused",
            request=httpx.Request("GET", "http://runner:8090/runtime/status"),
        )

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", boom)
    r = client.get("/runtime/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "degraded"
    assert body.get("runner_reachable") is False
    assert "unavailable" in (body.get("message") or "").lower()


def _bearer_headers(client_strict, prefix: str) -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert reg.status_code == 201, reg.text
    tok = reg.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_non_member_cannot_read_deployment_runtime(client_strict):
    ha = _bearer_headers(client_strict, "rtx")
    hb = _bearer_headers(client_strict, "rty")
    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={
            "name": "Isolated runtime",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "n1",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    )
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=ha).json()["id"]
    assert client_strict.get(f"/deployments/{did}/runtime", headers=hb).status_code == 404
    assert client_strict.get(f"/deployments/{did}/runtime/nodes", headers=hb).status_code == 404
    assert client_strict.get(f"/deployments/{did}/runtime/services", headers=hb).status_code == 404
    assert client_strict.get(f"/deployments/{did}/runtime/instructions", headers=hb).status_code == 404
    assert client_strict.get(f"/deployments/{did}/runtime/logs", headers=hb).status_code == 404
    assert client_strict.get(f"/deployments/{did}/runtime/services/{uuid.uuid4()}/logs", headers=hb).status_code == 404
    assert client_strict.get(f"/api/deployments/{did}/runtime", headers=hb).status_code == 404
    assert client_strict.get(f"/api/deployments/{did}/runtime/nodes", headers=hb).status_code == 404
