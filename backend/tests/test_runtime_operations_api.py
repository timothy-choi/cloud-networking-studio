"""Runtime operations API (Step 41) — RBAC and runner error mapping."""

from __future__ import annotations

import uuid
from uuid import UUID

import httpx
import pytest

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.services.deployment_runtime_resource_service import (
    replace_runtime_resources_from_payload,
)


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lab_with_service_row(client_strict, *, viewer_role: str):
    """Owner + second user on project; persisted service runtime row."""
    _, ha = _reg(client_strict, "ro")
    eb, hb = _reg(client_strict, "rb")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": viewer_role},
        ).status_code
        == 201
    )

    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={
            "name": "Ops lab",
            "project_id": pid,
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    nid = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "svc",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=ha).json()["id"]

    with SessionLocal() as db:
        replace_runtime_resources_from_payload(
            db,
            UUID(did),
            {
                "runtime_provider": "docker",
                "namespace_or_network": "cns-net",
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "svc",
                        "runtime_name": "cns-node-svc",
                        "status": "running",
                        "internal_url": "http://cns-node-svc:80",
                        "namespace_or_network": "cns-net",
                    },
                ],
            },
        )
        db.commit()

    svcs = client_strict.get(f"/deployments/{did}/runtime/services", headers=ha).json()["services"]
    rid = svcs[0]["id"]
    return ha, hb, did, rid, nid


def test_runtime_logs_requires_auth(client_strict):
    r = client_strict.get(f"/deployments/{uuid.uuid4()}/runtime/logs")
    assert r.status_code == 401


def test_viewer_can_read_runtime_logs(client_strict):
    ha, hb, did, _, _ = _lab_with_service_row(client_strict, viewer_role="viewer")
    assert client_strict.get(f"/deployments/{did}/runtime/logs", headers=ha).status_code == 200
    assert client_strict.get(f"/deployments/{did}/runtime/logs", headers=hb).status_code == 200


def test_viewer_cannot_run_traffic_tests(client_strict):
    ha, hb, did, rid, nid = _lab_with_service_row(client_strict, viewer_role="viewer")
    r = client_strict.post(
        f"/deployments/{did}/runtime/traffic-tests",
        headers=hb,
        json={
            "source_runtime_resource_id": rid,
            "target": str(nid),
            "protocol": "ping",
        },
    )
    assert r.status_code == 403


def test_member_can_run_health_check_and_traffic_stub(client_strict, monkeypatch):
    ha, hb, did, rid, nid = _lab_with_service_row(client_strict, viewer_role="member")

    def fake_health(self, deployment_id, topology_id, workload_node_id, *, project_id=None, body=None):
        return {
            "status": "passed",
            "target": "http://127.0.0.1:80/",
            "latency_ms": 12,
            "message": "ok",
        }

    def fake_traffic(self, deployment_id, body):
        return {
            "status": "unsupported",
            "source": body["source_node_id"],
            "target": body["target"],
            "protocol": body["protocol"],
            "output": "not supported yet",
            "latency_ms": 0,
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_health",
        fake_health,
    )
    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_traffic_test",
        fake_traffic,
    )
    monkeypatch.setattr(
        "app.services.runtime_operations_service.grc.effective_runtime_executor",
        lambda: "go",
    )

    hr = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/health-check",
        headers=hb,
    )
    assert hr.status_code == 200, hr.text
    assert hr.json()["status"] == "passed"

    tr = client_strict.post(
        f"/deployments/{did}/runtime/traffic-tests",
        headers=hb,
        json={
            "source_runtime_resource_id": rid,
            "target": str(nid),
            "protocol": "ping",
        },
    )
    assert tr.status_code == 200, tr.text
    assert tr.json()["status"] == "unsupported"


def test_runner_http_error_maps_to_502(client_strict, monkeypatch):
    ha, _, did, _, _ = _lab_with_service_row(client_strict, viewer_role="member")

    def boom(self, deployment_id, topology_id, *, tail, project_id=None):
        req = httpx.Request("GET", "http://runner/runtime/logs")
        resp = httpx.Response(502, request=req, json={"message": "bad gateway"})
        raise httpx.HTTPStatusError("502", request=req, response=resp)

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.get_runtime_deployment_logs",
        boom,
    )
    monkeypatch.setattr(
        "app.services.runtime_operations_service.grc.effective_runtime_executor",
        lambda: "go",
    )

    r = client_strict.get(f"/deployments/{did}/runtime/logs", headers=ha)
    assert r.status_code == 502
    assert "bad gateway" in r.json()["detail"].lower()


@pytest.mark.parametrize(
    "path",
    [
        "/deployments/{deployment_id}/runtime/logs",
        "/deployments/{deployment_id}/runtime/services/{service_id}/logs",
    ],
)
def test_runtime_logs_paths_require_auth(client_strict, path):
    did, sid = uuid.uuid4(), uuid.uuid4()
    p = path.replace("{deployment_id}", str(did)).replace("{service_id}", str(sid))
    assert client_strict.get(p).status_code == 401
