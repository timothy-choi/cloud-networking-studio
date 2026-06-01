"""Tests for AI infrastructure advisor (Feature 61)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services import ai_infrastructure_advisor_service as advisor_svc
from app.services.infra_apply_safety import GCP_APPLY_MACHINE_TYPES

GCP_SA = {
    "type": "service_account",
    "project_id": "my-gcp-project",
    "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
    "client_email": "cns@test.iam.gserviceaccount.com",
}


def _node(
    *,
    name: str = "web",
    node_type: NodeType = NodeType.HOST,
    image: str = "nginx:latest",
    config: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        node_type=node_type,
        image=image,
        config=config or {},
    )


def _topology(*nodes) -> SimpleNamespace:
    return SimpleNamespace(nodes=list(nodes), name="lab-topology", id=uuid.uuid4(), project_id=uuid.uuid4())


def test_advisor_context_excludes_secrets():
    topo = _topology(
        _node(name="app", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}),
    )
    context = advisor_svc.build_advisor_context(topo)  # type: ignore[arg-type]
    serialized = json.dumps(context, default=str).lower()
    assert "encrypted_secret" not in serialized
    assert "private_key" not in serialized
    assert "-----begin" not in serialized
    assert "password" not in serialized


def test_credential_profile_lookup_uses_keyword_only_arguments(monkeypatch):
    topo = _topology(
        _node(name="app", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}),
    )
    profile_id = uuid.uuid4()
    calls: dict[str, uuid.UUID] = {}

    def fake_get_profile_for_project(db, *, profile_id: uuid.UUID, project_id: uuid.UUID):
        calls["profile_id"] = profile_id
        calls["project_id"] = project_id
        return SimpleNamespace(
            id=profile_id,
            name="Stage GCP",
            provider="gcp",
            credential_type="gcp_service_account_json",
            gcp_project_id="my-gcp-project",
            validation_status="valid",
            metadata_json={
                "environment": "stage",
                "project_id": "my-gcp-project",
                "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
                "token": "super-secret-token",
                "nested": {"client_secret": "hidden", "region": "us-central1"},
            },
        )

    monkeypatch.setattr(advisor_svc.profile_svc, "get_profile_for_project", fake_get_profile_for_project)

    context = advisor_svc.build_advisor_context(  # type: ignore[arg-type]
        topo,
        db=object(),  # only passed through to the lookup spy
        credential_profile_id=str(profile_id),
    )

    assert calls == {"profile_id": profile_id, "project_id": topo.project_id}
    profile = context["credential_profile"]
    assert profile["name"] == "Stage GCP"
    assert profile["provider"] == "gcp"
    assert profile["credential_type"] == "gcp_service_account_json"
    assert profile["validation_status"] == "valid"
    assert profile["project_id"] == "my-gcp-project"
    assert profile["metadata"] == {
        "environment": "stage",
        "project_id": "my-gcp-project",
        "nested": {"region": "us-central1"},
    }
    serialized = json.dumps(context, default=str).lower()
    assert "private_key" not in serialized
    assert "super-secret-token" not in serialized
    assert "client_secret" not in serialized


def test_heuristic_advisor_returns_structured_advice():
    topo = _topology(
        _node(name="cli-edge", config={"resource_cpu": 0.25, "resource_memory_mb": 256, "replicas": 1}),
        _node(name="svc-origin", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}),
    )
    advice = advisor_svc.generate_ai_infrastructure_advice(topo)  # type: ignore[arg-type]
    assert advice["summary"]
    assert advice["explanation"]
    assert advice["advisory_only"] is True
    assert "recommended_overrides" in advice
    overrides = advice["recommended_overrides"]
    assert overrides["machine_type"] in GCP_APPLY_MACHINE_TYPES
    assert overrides["strategy_valid"] is True


def test_mocked_advisor_backend():
    topo = _topology(_node(config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}))

    def mock_advisor(_context: dict) -> dict:
        return {
            "summary": "Mock summary for test topology.",
            "risks": ["Mock risk"],
            "suggestions": ["Mock suggestion"],
            "explanation": "Mock beginner explanation.",
        }

    advisor_svc.set_advisor_fn(mock_advisor)
    try:
        advice = advisor_svc.generate_ai_infrastructure_advice(topo)  # type: ignore[arg-type]
        assert advice["summary"] == "Mock summary for test topology."
        assert advice["advisor_mode"] == "mock"
        assert advice["risks"] == ["Mock risk"]
    finally:
        advisor_svc.set_advisor_fn(None)


def test_validate_overrides_rejects_invalid_machine_type():
    topo = _topology(
        _node(name="heavy", config={"resource_cpu": 2, "resource_memory_mb": 9000, "replicas": 1}),
    )
    context = advisor_svc.build_advisor_context(topo, selected_machine_type="e2-micro")  # type: ignore[arg-type]
    overrides = advisor_svc.validate_recommended_overrides(context, topology=topo)  # type: ignore[arg-type]
    if overrides["machine_type"] == "e2-micro":
        assert overrides["machine_type_valid"] is False


def test_ai_infrastructure_advice_api(client_strict, engine_db):
    email = f"aiadv{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "AiAdv"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "ai-advisor-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    assert topo.status_code == 201, topo.text
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={
            "name": "app",
            "node_type": "host",
            "image": "nginx",
            "config": {"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1},
        },
    )

    resp = client_strict.post(
        f"/topologies/{topo_id}/ai-infrastructure-advice",
        headers=headers,
        json={"provider": "gcp", "selected_strategy": "docker-vm"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]
    assert body["explanation"]
    assert body["advisory_only"] is True
    assert body["recommended_overrides"]["strategy"] == "docker-vm"
    assert body["recommended_overrides"]["strategy_valid"] is True

    serialized = json.dumps(body).lower()
    assert "private_key" not in serialized
    assert "encrypted_secret" not in serialized


def test_ai_infrastructure_advice_api_with_credential_profile(client_strict, engine_db):
    captured_context: dict | None = None

    def capture_advisor(context: dict) -> dict:
        nonlocal captured_context
        captured_context = context
        return {
            "summary": "Advisor saw scrubbed credential profile metadata.",
            "risks": [],
            "suggestions": ["Credential metadata is advisory context only."],
            "explanation": "No secret material is required for infrastructure advice.",
        }

    email = f"aiadvprof{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "AiAdv Profile"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]

    profile = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "Stage GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(GCP_SA),
            "metadata": {
                "environment": "stage",
                "project_id": "my-gcp-project",
                "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
                "token": "super-secret-token",
                "nested": {"client_secret": "hidden", "region": "us-central1"},
            },
        },
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["id"]

    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "ai-advisor-profile-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    assert topo.status_code == 201, topo.text
    topo_id = topo.json()["id"]
    node = client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={
            "name": "app",
            "node_type": "host",
            "image": "nginx",
            "config": {"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1},
        },
    )
    assert node.status_code == 201, node.text

    advisor_svc.set_advisor_fn(capture_advisor)
    try:
        resp = client_strict.post(
            f"/topologies/{topo_id}/ai-infrastructure-advice",
            headers=headers,
            json={
                "provider": "gcp",
                "selected_strategy": "docker-vm",
                "credential_profile_id": profile_id,
            },
        )
    finally:
        advisor_svc.set_advisor_fn(None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == "Advisor saw scrubbed credential profile metadata."
    assert body["advisory_only"] is True
    assert captured_context is not None
    credential_profile = captured_context["credential_profile"]
    assert credential_profile == {
        "id": profile_id,
        "name": "Stage GCP",
        "provider": "gcp",
        "credential_type": "gcp_service_account_json",
        "project_id": "my-gcp-project",
        "validation_status": "valid",
        "metadata": {
            "environment": "stage",
            "project_id": "my-gcp-project",
            "nested": {"region": "us-central1"},
        },
    }

    serialized_context = json.dumps(captured_context, default=str).lower()
    serialized_body = json.dumps(body, default=str).lower()
    for forbidden in ("private_key", "encrypted_secret", "-----begin", "super-secret-token", "client_secret"):
        assert forbidden not in serialized_context
        assert forbidden not in serialized_body
