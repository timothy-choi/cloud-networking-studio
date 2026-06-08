"""Tests for runtime strategy layer (Step 64)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services import runtime_strategy_plan_service as runtime_plan_svc
from app.services.runtime_strategy_registry import (
    assert_runtime_strategy_for_generation,
    list_runtime_strategies,
    require_runtime_strategy,
)


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


def test_runtime_strategy_registry_returns_all_strategies():
    strategies = list_runtime_strategies()
    ids = {strategy.id for strategy in strategies}
    assert ids == {"docker-vm", "docker-multi-vm", "k8s-cluster"}

    docker_vm = require_runtime_strategy("docker-vm")
    assert docker_vm.status == "available"
    assert docker_vm.runtime_provider == "remote_docker"
    assert docker_vm.host_model == "single_host"
    assert docker_vm.deployment_model == "docker_compose"
    assert docker_vm.supports_runtime_target_generation is True
    assert docker_vm.supports_external_deployment is True

    docker_multi = require_runtime_strategy("docker-multi-vm")
    assert docker_multi.status == "planning_only"
    assert docker_multi.runtime_provider == "remote_docker_cluster"
    assert docker_multi.supports_runtime_target_generation is False
    assert docker_multi.supports_external_deployment is False

    k8s = require_runtime_strategy("k8s-cluster")
    assert k8s.status == "future"
    assert k8s.runtime_provider == "kubernetes"
    assert k8s.host_model == "cluster"


def test_docker_vm_strategy_plan_for_one_host_topology():
    topo = _topology(
        _node(name="cli-edge", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
        _node(name="svc-origin", config={"resource_cpu": 0.5, "resource_memory_mb": 512}),
    )
    from app.services import topology_placement_planner_service as placement_svc
    from app.services import deployment_strategy_recommendation_service as strategy_svc

    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    strategy = strategy_svc.recommend_strategy_from_plan(plan)
    runtime_plan = runtime_plan_svc.build_runtime_strategy_plan(
        placement_plan=plan,
        strategy_recommendation=strategy,
    )

    assert runtime_plan["recommended_runtime_strategy"] == "docker-vm"
    assert runtime_plan["runtime_strategy"]["runtime_provider"] == "remote_docker"
    assert runtime_plan["host_count"] == 1
    assert runtime_plan["can_generate_infrastructure"] is True
    assert runtime_plan["generation_block_reason"] is None
    labels = {item["key"] for item in runtime_plan["runtime_target_requirements"]}
    assert {"runtime_targets", "docker", "docker_compose", "ssh_credential", "remote_workdir"} <= labels
    assert runtime_plan["capabilities"]["runtime_target_generation"] is True
    assert runtime_plan["capabilities"]["external_deployment"] is True


def test_docker_multi_vm_strategy_plan_for_multi_host_topology():
    topo = _topology(
        _node(name="worker-a", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
        _node(name="worker-b", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
    )
    from app.services import topology_placement_planner_service as placement_svc
    from app.services import deployment_strategy_recommendation_service as strategy_svc

    constraints = [{"constraint_type": "different_host", "node_a": "worker-a", "node_b": "worker-b"}]
    plan = placement_svc.build_placement_plan(
        topo,
        machine_type="e2-micro",
        constraints=constraints,
    )  # type: ignore[arg-type]
    strategy = strategy_svc.recommend_strategy_from_plan(plan)
    runtime_plan = runtime_plan_svc.build_runtime_strategy_plan(
        placement_plan=plan,
        strategy_recommendation=strategy,
        constraints=constraints,
        selected_strategy_id="docker-multi-vm",
    )

    assert runtime_plan["selected_runtime_strategy"] == "docker-multi-vm"
    assert runtime_plan["host_count"] == 2
    assert runtime_plan["can_generate_infrastructure"] is False
    assert "planning-only" in (runtime_plan["generation_block_reason"] or "").lower()
    assert runtime_plan["unsupported_features"]
    assert any("Multi-host" in feature for feature in runtime_plan["unsupported_features"])
    labels = {item["key"] for item in runtime_plan["runtime_target_requirements"]}
    assert "overlay_network" in labels


def test_assert_runtime_strategy_blocks_planning_only_and_future():
    with pytest.raises(ValueError, match="planning-only"):
        assert_runtime_strategy_for_generation("docker-multi-vm", host_count=2)
    with pytest.raises(ValueError, match="future"):
        assert_runtime_strategy_for_generation("k8s-cluster", host_count=1)


def test_assert_runtime_strategy_validates_host_model():
    with pytest.raises(ValueError, match="single-host"):
        assert_runtime_strategy_for_generation("docker-vm", host_count=2)


def test_list_runtime_strategies_api(client_strict, engine_db):
    response = client_strict.get("/runtime-strategies")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 3
    docker_vm = next(item for item in items if item["id"] == "docker-vm")
    assert docker_vm["runtime_provider"] == "remote_docker"
    assert docker_vm["supports_runtime_target_generation"] is True


def test_runtime_strategy_plan_api(client_strict, engine_db):
    email = f"runtime{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Runtime"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "runtime-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    for name, cpu, memory in [("cli-edge", 0.25, 256), ("svc-origin", 0.5, 512)]:
        client_strict.post(
            f"/topologies/{topo_id}/nodes",
            headers=headers,
            json={
                "name": name,
                "node_type": "host",
                "image": "nginx:latest",
                "config": {"resource_cpu": cpu, "resource_memory_mb": memory, "resource_disk_gb": 5},
            },
        )

    plan = client_strict.get(f"/topologies/{topo_id}/runtime-strategy-plan", headers=headers)
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["recommended_runtime_strategy"] == "docker-vm"
    assert body["runtime_strategy"]["deployment_model"] == "docker_compose"
    assert body["can_generate_infrastructure"] is True
    assert body["runtime_target_requirements"]


def test_generate_blocked_for_planning_only_runtime_strategy(client_strict, engine_db):
    email = f"runtimeblk{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "RuntimeBlk"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "runtime-block",
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
    assert "runtime strategy" in generated.text.lower()
    assert "planning-only" in generated.text.lower()
