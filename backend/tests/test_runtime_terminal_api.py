"""Step 49: terminal sessions and integration endpoints."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.services.deployment_runtime_resource_service import replace_runtime_resources_from_payload

TOPO = {
    "name": "Terminal lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_with_service(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "web",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": None,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": n["id"],
            "target_node_id": n["id"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy").json()
    return tid, dep["id"], n["id"]


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lab_service_row(client_strict):
    _, ha = _reg(client_strict, "termo")
    eb, hb = _reg(client_strict, "termv")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "viewer"},
        ).status_code
        == 201
    )
    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={**TOPO, "project_id": pid},
    ).json()["id"]
    nid = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "web",
            "node_type": NodeType.HOST.value,
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
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "web",
                        "runtime_name": "cns-node-web",
                        "internal_url": "http://cns-node-web:80",
                    },
                ],
            },
        )
        db.commit()
    rid = client_strict.get(f"/deployments/{did}/runtime/services", headers=ha).json()["services"][0]["id"]
    return ha, hb, did, rid


def test_integration_endpoint_returns_snippets(client):
    _, did, _ = _topology_with_service(client)
    r = client.get(f"/deployments/{did}/runtime/integration")
    assert r.status_code == 200
    body = r.json()
    assert body["deployment_id"] == did
    assert len(body["snippets"]) >= 1
    assert body["env_vars"]["CNS_DEPLOYMENT_ID"] == did


def test_mapping_endpoint_returns_rows(client):
    _, did, nid = _topology_with_service(client)
    r = client.get(f"/deployments/{did}/runtime/mapping")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) >= 1
    assert any(str(row.get("topology_node_id")) == nid for row in rows)


def test_viewer_cannot_open_terminal(client_strict):
    ha, hb, did, rid = _lab_service_row(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/terminal",
        headers=hb,
    )
    assert r.status_code == 403


def test_member_can_create_terminal_session(client_strict):
    ha, _, did, rid = _lab_service_row(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/terminal",
        headers=ha,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session_id"]
    assert body["websocket_path"].startswith("/terminal-sessions/")
    close = client_strict.delete(f"/terminal-sessions/{body['session_id']}", headers=ha)
    assert close.status_code == 200
