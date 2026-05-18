"""Onboarding API: auth, status, steps, reset, and optional start-demo."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


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
