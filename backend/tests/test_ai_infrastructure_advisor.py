"""Tests for AI infrastructure advisor (Feature 61)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services import ai_infrastructure_advisor_service as advisor_svc
from app.services.infra_apply_safety import GCP_APPLY_MACHINE_TYPES


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
