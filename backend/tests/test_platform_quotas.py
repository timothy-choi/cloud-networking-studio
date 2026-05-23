"""Quotas, rate limits, and cleanup policies (Step 53B)."""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.models.topology import NodeType
from app.services.rate_limit_service import reset_rate_limits_for_tests

TOPOLOGY_BODY = {
    "name": "Quota Lab",
    "description": "quota test",
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


def _register(client_strict, prefix: str = "q") -> tuple[dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Q"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    return h, pid


def test_quota_prevents_too_many_active_deployments(client_strict, monkeypatch):
    """Isolated project so prior session deployments do not affect the quota count."""
    monkeypatch.setattr(settings, "quota_max_active_deployments_per_project", 1)
    ha, _pid = _register(client_strict, "qa")
    t1 = _topology_with_node(client_strict, ha)
    t2 = _topology_with_node(client_strict, ha)
    assert client_strict.post(f"/topologies/{t1}/deploy", headers=ha).status_code == 201
    r2 = client_strict.post(f"/topologies/{t2}/deploy", headers=ha)
    assert r2.status_code == 403
    body = r2.json()
    assert body["error"]["code"] == "QUOTA_EXCEEDED"


def test_rate_limit_returns_rate_limited(client, monkeypatch):
    monkeypatch.setenv("CNS_DISABLE_RATE_LIMITS", "0")
    reset_rate_limits_for_tests()
    monkeypatch.setattr(settings, "rate_limit_auth_per_ip", 1)
    email = f"rl{uuid.uuid4().hex[:8]}@example.com"
    assert client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "RL"},
    ).status_code == 201
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


def test_cleanup_endpoint_enforces_permissions(client_strict, monkeypatch):
    ha, _pid = _register(client_strict, "ca")
    tid = _topology_with_node(client_strict, ha)
    r = client_strict.post(f"/topologies/{tid}/deploy", headers=ha)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    hb, _ = _register(client_strict, "cb")
    assert client_strict.get(f"/deployments/{did}/cleanup-status", headers=hb).status_code == 404
    st = client_strict.get(f"/deployments/{did}/cleanup-status", headers=ha)
    assert st.status_code == 200
    assert st.json()["deployment_id"] == did
    cleanup = client_strict.post(f"/deployments/{did}/cleanup", headers=ha)
    assert cleanup.status_code == 200
    assert cleanup.json()["ok"] is True


def test_terminal_session_quota(client_strict, monkeypatch):
    monkeypatch.setattr(settings, "terminal_max_sessions_per_user", 1)
    ha, pid = _register(client_strict, "tm")
    q = client_strict.get(f"/projects/{pid}/quotas", headers=ha)
    assert q.status_code == 200
    assert q.json()["limits"]["max_terminal_sessions_per_user"] == 1
    assert q.json()["usage"]["terminal_sessions"] == 0


def test_project_quotas_endpoint(client):
    tid = _topology_with_node(client)
    topo = client.get(f"/topologies/{tid}").json()
    pid = topo["project_id"]
    q = client.get(f"/projects/{pid}/quotas")
    assert q.status_code == 200
    body = q.json()
    assert body["limits"]["max_active_deployments_per_project"] >= 1
    assert "usage" in body
