"""Onboarding API: auth, status, steps, reset, and optional start-demo."""

from __future__ import annotations

import uuid

from app.models.topology import NodeType
from fastapi.testclient import TestClient

TOPO_FOR_DEPLOY = {
    "name": "Onboard sticky lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_deploy(client_strict: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    pid = client_strict.get("/projects", headers=headers).json()[0]["id"]
    tid = client_strict.post(
        "/topologies",
        headers=headers,
        json={**TOPO_FOR_DEPLOY, "project_id": pid},
    ).json()["id"]
    na = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={
            "name": "host-a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nb = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=headers,
        json={
            "name": "service-b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    client_strict.post(
        f"/topologies/{tid}/links",
        headers=headers,
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    d = client_strict.post(f"/topologies/{tid}/deploy", headers=headers)
    assert d.status_code == 201, d.text
    return tid, d.json()["id"]


def _step(data: dict, sid: str) -> dict:
    return next(s for s in data["steps"] if s["id"] == sid)


def _register(client: TestClient, prefix: str = "ob") -> tuple[str, dict[str, str]]:
    email = f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "longenoughpw", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_onboarding_requires_auth(client_strict: TestClient):
    r = client_strict.get("/onboarding/status")
    assert r.status_code == 401


def test_onboarding_status_get_and_reset(client_strict: TestClient):
    _, h = _register(client_strict)
    r = client_strict.get("/onboarding/status", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["has_seen_onboarding"] is False
    assert isinstance(data["completed_steps"], list)
    assert len(data["steps"]) == 8
    ids = [s["id"] for s in data["steps"]]
    assert "project" in ids
    assert data["steps"][0]["completed"] is True  # auto: membership from register

    r2 = client_strict.post("/onboarding/complete-step", headers=h, json={"step": "topology"})
    assert r2.status_code == 200
    assert "topology" in r2.json()["completed_steps"]

    r3 = client_strict.post("/onboarding/status", headers=h, json={"has_seen_onboarding": True})
    assert r3.status_code == 200
    assert r3.json()["has_seen_onboarding"] is True

    r4 = client_strict.post("/onboarding/reset", headers=h)
    assert r4.status_code == 200
    body = r4.json()
    assert body["has_seen_onboarding"] is False
    assert body["completed_steps"] == []


def test_onboarding_complete_step_unknown(client_strict: TestClient):
    _, h = _register(client_strict)
    r = client_strict.post("/onboarding/complete-step", headers=h, json={"step": "not-a-real-step"})
    assert r.status_code == 400


def test_onboarding_status_replace_completed_steps(client_strict: TestClient):
    _, h = _register(client_strict)
    r = client_strict.post(
        "/onboarding/status",
        headers=h,
        json={"completed_steps": ["topology", "deploy"]},
    )
    assert r.status_code == 200
    steps = {s["id"]: s["completed"] for s in r.json()["steps"]}
    assert steps["topology"] is True
    assert steps["deploy"] is True


def test_start_demo_uses_template_and_deploys(client_strict: TestClient):
    _, h = _register(client_strict, "demo")
    r = client_strict.post("/onboarding/start-demo", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "project_id" in body
    assert "topology_id" in body
    assert "deployment_id" in body
    assert body.get("resumed") in (True, False)

    r2 = client_strict.post("/onboarding/start-demo", headers=h)
    assert r2.status_code == 201, r2.text
    assert r2.json().get("resumed") is True


def test_onboarding_deploy_sticky_after_destroy(client_strict: TestClient):
    _, h = _register(client_strict, "stk1")
    _, did = _topology_deploy(client_strict, h)
    s1 = client_strict.get("/onboarding/status", headers=h).json()
    assert _step(s1, "deploy")["completed"] is True
    assert "deploy" in s1["completed_steps"]

    assert client_strict.post(f"/deployments/{did}/destroy", headers=h).status_code == 200

    s2 = client_strict.get("/onboarding/status", headers=h).json()
    assert _step(s2, "deploy")["completed"] is True
    assert "deploy" in s2["completed_steps"]
    assert _step(s2, "destroy_deployment")["completed"] is True
    assert "destroy_deployment" in s2["completed_steps"]


def test_onboarding_expose_sticky_after_destroy(client_strict: TestClient):
    _, h = _register(client_strict, "stk2")
    _, did = _topology_deploy(client_strict, h)
    assert (
        client_strict.post("/onboarding/complete-step", headers=h, json={"step": "expose_service"}).status_code
        == 200
    )
    s1 = client_strict.get("/onboarding/status", headers=h).json()
    assert "expose_service" in s1["completed_steps"]

    assert client_strict.post(f"/deployments/{did}/destroy", headers=h).status_code == 200

    s2 = client_strict.get("/onboarding/status", headers=h).json()
    assert _step(s2, "expose_service")["completed"] is True
    assert "expose_service" in s2["completed_steps"]


def test_onboarding_reset_clears_persisted_completed_steps(client_strict: TestClient):
    _, h = _register(client_strict, "stk3")
    _, did = _topology_deploy(client_strict, h)
    s_live = client_strict.get("/onboarding/status", headers=h).json()
    assert "deploy" in s_live["completed_steps"]

    assert client_strict.post(f"/deployments/{did}/destroy", headers=h).status_code == 200

    r_reset = client_strict.post("/onboarding/reset", headers=h)
    assert r_reset.status_code == 200
    assert r_reset.json()["completed_steps"] == []

    s_after = client_strict.get("/onboarding/status", headers=h).json()
    assert "deploy" not in s_after["completed_steps"]
    # A STOPPED deployment row may still exist, so live auto can re-persist ``destroy_deployment`` on GET.
