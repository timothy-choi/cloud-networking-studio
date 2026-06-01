"""Tests for deployment strategy recommendation (Feature 60)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services.deployment_strategy_registry import assert_strategy_available, get_strategy
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services import topology_placement_planner_service as placement_svc


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


def test_small_topology_recommends_docker_vm():
    topo = _topology(
        _node(name="cli-edge", config={"resource_cpu": 0.25, "resource_memory_mb": 256, "replicas": 1}),
        _node(name="svc-origin", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}),
    )
    rec = strategy_svc.build_strategy_recommendation(topo)  # type: ignore[arg-type]
    assert rec["recommended_strategy"] == "docker-vm"
    assert "Topology fits on a single host" in rec["reasons"]
    assert "docker-multi-vm" in rec["alternatives"]


def test_multi_host_topology_recommends_docker_multi_vm():
    topo = _topology(
        _node(name="a", config={"resource_cpu": 1, "resource_memory_mb": 3000, "replicas": 1}),
        _node(name="b", config={"resource_cpu": 1, "resource_memory_mb": 3000, "replicas": 1}),
    )
    rec = strategy_svc.build_strategy_recommendation(topo, machine_type="e2-medium")  # type: ignore[arg-type]
    assert rec["recommended_strategy"] == "docker-multi-vm"
    assert rec["evaluation"]["host_count"] >= 2
    assert "k8s-cluster" in rec["alternatives"]


def test_high_replica_topology_includes_k8s_alternative():
    topo = _topology(
        _node(
            name="worker",
            config={"resource_cpu": 0.25, "resource_memory_mb": 256, "replicas": 6},
        ),
    )
    rec = strategy_svc.build_strategy_recommendation(topo)  # type: ignore[arg-type]
    assert rec["recommended_strategy"] == "docker-vm"
    assert "k8s-cluster" in rec["alternatives"]
    assert rec["evaluation"]["total_replicas"] >= 6


def test_strategy_registry_statuses():
    assert get_strategy("docker-vm").status == "available"
    assert get_strategy("docker-multi-vm").status == "planning_only"
    assert get_strategy("k8s-cluster").status == "future"


def test_assert_strategy_available_blocks_planning_only():
    with pytest.raises(ValueError, match="planning-only"):
        assert_strategy_available("docker-multi-vm")


def test_assert_strategy_available_blocks_future():
    with pytest.raises(ValueError, match="not available yet"):
        assert_strategy_available("k8s-cluster")


def test_generate_payload_uses_docker_vm_template():
    topo = _topology(_node(config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}))
    draft = placement_svc.build_generate_deployment_payload(topo, template_id="docker-vm")  # type: ignore[arg-type]
    assert draft["template_id"] == "docker-vm"


def test_strategy_recommendation_api(client_strict, engine_db):
    email = f"strat{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Strat"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "strategy-lab",
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

    rec = client_strict.get(f"/topologies/{topo_id}/strategy-recommendation", headers=headers)
    assert rec.status_code == 200, rec.text
    body = rec.json()
    assert body["recommended_strategy"] == "docker-vm"
    assert isinstance(body["reasons"], list)
    assert isinstance(body["alternatives"], list)


def test_generate_rejects_planning_only_strategy(client_strict, engine_db):
    email = f"stratrej{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "StratRej"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "reject-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={"name": "app", "node_type": "host", "image": "nginx", "config": {"resource_memory_mb": 512}},
    )

    generated = client_strict.post(
        f"/topologies/{topo_id}/generate-infrastructure-deployment",
        headers=headers,
        json={"provider": "gcp", "template_id": "docker-multi-vm"},
    )
    assert generated.status_code == 400, generated.text
    assert "planning-only" in generated.text.lower()
