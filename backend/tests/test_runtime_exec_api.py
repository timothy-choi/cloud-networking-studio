"""Safe runtime exec and restart (Step 42) — RBAC, allowlist, persistence."""

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
    _, ha = _reg(client_strict, "ex")
    eb, hb = _reg(client_strict, "exb")
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
            "name": "Exec lab",
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
    return ha, hb, did, rid


def test_exec_requires_auth(client_strict):
    did, sid = uuid.uuid4(), uuid.uuid4()
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{sid}/exec",
        json={"command": "whoami", "timeout_seconds": 10},
    )
    assert r.status_code == 401


def test_viewer_cannot_exec_or_restart(client_strict):
    _, hb, did, rid = _lab_with_service_row(client_strict, viewer_role="viewer")
    ex = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/exec",
        headers=hb,
        json={"command": "whoami", "timeout_seconds": 10},
    )
    assert ex.status_code == 403
    rs = client_strict.post(f"/deployments/{did}/runtime/services/{rid}/restart", headers=hb)
    assert rs.status_code == 403
    # Owner can still hit routes (may be unsupported without go)
    assert client_strict.get(f"/deployments/{did}/runtime/exec-results", headers=hb).status_code == 200


def test_member_dangerous_exec_rejected_and_persisted(client_strict, monkeypatch):
    _, hb, did, rid = _lab_with_service_row(client_strict, viewer_role="member")
    monkeypatch.setattr(
        "app.services.runtime_exec_service.grc.effective_runtime_executor",
        lambda: "go",
    )

    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/exec",
        headers=hb,
        json={"command": "rm -f /tmp/x", "timeout_seconds": 10},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "rejected"
    assert "not allowed" in (j.get("message") or "").lower()

    lst = client_strict.get(f"/deployments/{did}/runtime/exec-results", headers=hb).json()
    assert lst["deployment_id"] == did
    assert any(it["command"] == "rm -f /tmp/x" and it["status"] == "rejected" for it in lst["items"])

    eid = j["id"]
    one = client_strict.get(f"/deployments/{did}/runtime/exec-results/{eid}", headers=hb).json()
    assert one["id"] == eid
    assert one["status"] == "rejected"


def test_member_allowed_exec_calls_runner(client_strict, monkeypatch):
    _, hb, did, rid = _lab_with_service_row(client_strict, viewer_role="member")

    def fake_exec(self, deployment_id, topology_id, workload_node_id, body, *, project_id=None):
        return {
            "deployment_id": str(deployment_id),
            "service_id": workload_node_id,
            "command": body["command"],
            "status": "succeeded",
            "exit_code": 0,
            "stdout": "root",
            "stderr": "",
            "started_at": "2020-01-01T00:00:00Z",
            "finished_at": "2020-01-01T00:00:01Z",
            "runtime_provider": "docker",
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_exec",
        fake_exec,
    )
    monkeypatch.setattr(
        "app.services.runtime_exec_service.grc.effective_runtime_executor",
        lambda: "go",
    )

    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/exec",
        headers=hb,
        json={"command": "whoami", "timeout_seconds": 10},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "succeeded"
    assert j["stdout"] == "root"
    assert j["exit_code"] == 0

    eid = j["id"]
    one = client_strict.get(f"/deployments/{did}/runtime/exec-results/{eid}", headers=hb).json()
    assert one["command"] == "whoami"


def test_restart_member_calls_runner(client_strict, monkeypatch):
    _, hb, did, rid = _lab_with_service_row(client_strict, viewer_role="member")

    def fake_restart(self, deployment_id, topology_id, workload_node_id, *, project_id=None):
        return {
            "status": "succeeded",
            "message": "container restarted",
            "runtime_provider": "docker",
        }

    monkeypatch.setattr(
        "app.runtime.go_runner_client.GoRunnerClient.post_runtime_service_restart",
        fake_restart,
    )
    monkeypatch.setattr(
        "app.services.runtime_exec_service.grc.effective_runtime_executor",
        lambda: "go",
    )

    r = client_strict.post(f"/deployments/{did}/runtime/services/{rid}/restart", headers=hb)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "succeeded"


def test_exec_list_requires_auth(client_strict):
    did = uuid.uuid4()
    assert client_strict.get(f"/deployments/{did}/runtime/exec-results").status_code == 401
