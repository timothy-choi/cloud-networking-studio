"""Platform NFR hardening tests (Step 53A)."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType

TOPOLOGY_BODY = {
    "name": "NFR Lab",
    "description": "platform nfr",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _minimal_topology(client) -> str:
    r = client.post("/topologies", json=TOPOLOGY_BODY)
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
    )
    return tid


def test_request_id_generated_and_returned(client):
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid
    assert len(rid) >= 8


def test_structured_error_includes_code_and_request_id(client):
    missing = uuid.uuid4()
    r = client.get(f"/deployments/{missing}")
    assert r.status_code == 404
    body = r.json()
    assert body.get("error", {}).get("code") == "NOT_FOUND"
    assert body.get("error", {}).get("request_id")
    assert body.get("detail") == "Not found"


def test_deploy_creates_audit_log_and_timeline(client):
    tid = _minimal_topology(client)
    d = client.post(f"/topologies/{tid}/deploy")
    assert d.status_code == 201, d.text
    did = d.json()["id"]

    timeline = client.get(f"/deployments/{did}/timeline")
    assert timeline.status_code == 200
    events = timeline.json()["events"]
    assert len(events) >= 2
    types = [e["event_type"] for e in events]
    assert "DEPLOY_REQUESTED" in types
    assert "DEPLOY_SUCCEEDED" in types
    times = [e["created_at"] for e in events]
    assert times == sorted(times)

    audit = client.get(f"/deployments/{did}/audit-logs")
    assert audit.status_code == 200
    actions = [row["action"] for row in audit.json()["items"]]
    assert "topology.deploy" in actions


def test_destroy_creates_audit_log(client):
    tid = _minimal_topology(client)
    did = client.post(f"/topologies/{tid}/deploy").json()["id"]
    destroy = client.post(f"/deployments/{did}/destroy")
    assert destroy.status_code == 200
    audit = client.get(f"/deployments/{did}/audit-logs")
    actions = [row["action"] for row in audit.json()["items"]]
    assert "deployment.destroy" in actions


def test_iac_export_creates_audit_log(client):
    tid = _minimal_topology(client)
    r = client.get(f"/topologies/{tid}/exports/docker-compose")
    assert r.status_code == 200
    topo = client.get(f"/topologies/{tid}").json()
    pid = topo["project_id"]
    logs = client.get(f"/projects/{pid}/audit-logs")
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()["items"]]
    assert "iac_export.download" in actions


def _register(client_strict, prefix: str = "nfr") -> tuple[str, dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "NFR"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    pid = client_strict.get("/projects", headers={"Authorization": f"Bearer {tok}"}).json()[0]["id"]
    return email, {"Authorization": f"Bearer {tok}"}, pid


def test_unauthorized_audit_log_access_blocked(client_strict):
    _, ha, pid = _register(client_strict, "oa")
    _, hb, _ = _register(client_strict, "ob")
    assert client_strict.get(f"/projects/{pid}/audit-logs", headers=hb).status_code == 404
