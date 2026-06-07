"""Tests for generic topology placement planner (Feature 59A)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services import topology_placement_planner_service as placement_svc
from app.services.node_resource_metadata import NODE_ROLES, EXPOSURE_VALUES
from app.services.node_runtime_config import NodeConfigValidationError, validate_and_normalize_node_config


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


def test_estimate_simple_topology():
    topo = _topology(
        _node(name="web", config={"resource_cpu": 1, "resource_memory_mb": 1024, "resource_disk_gb": 10, "replicas": 1}),
        _node(name="core-switch", node_type=NodeType.SWITCH),
    )
    estimate = placement_svc.build_resource_estimate(topo)  # type: ignore[arg-type]
    assert estimate["workload_node_count"] == 1
    assert estimate["total_cpu"] == 1.0
    assert estimate["total_memory_mb"] == 1024
    assert estimate["placement_unit_count"] == 1
    node = estimate["nodes"][0]
    assert node["node_name"] == "web"
    assert node["node_id"]
    assert node["resource_cpu"] == 1
    assert node["resource_memory_mb"] == 1024
    assert node["resource_disk_gb"] == 10
    assert node["replicas"] == 1
    assert node["resource_source"] == "explicit"


def test_estimate_uses_preferred_nested_resource_config():
    topo = _topology(
        _node(
            name="api",
            config={
                "resources": {"cpu": 1.5, "memory_mb": 1024, "disk_gb": 10, "replicas": 2},
                "exposure": "private",
                "stateful": True,
                "required_ports": [8080],
            },
        ),
    )
    estimate = placement_svc.build_resource_estimate(topo)  # type: ignore[arg-type]
    node = estimate["nodes"][0]
    assert estimate["total_cpu"] == 3.0
    assert estimate["total_memory_mb"] == 2048
    assert estimate["total_disk_gb"] == 20
    assert node["resource_cpu"] == 1.5
    assert node["resource_memory_mb"] == 1024
    assert node["resource_disk_gb"] == 10
    assert node["replicas"] == 2
    assert node["resource_source"] == "explicit"


def test_estimate_falls_back_to_defaults_when_resources_missing():
    topo = _topology(_node(name="web", image="nginx:alpine", config={}))
    estimate = placement_svc.build_resource_estimate(topo)  # type: ignore[arg-type]
    node = estimate["nodes"][0]
    assert node["resource_cpu"] == 0.25
    assert node["resource_memory_mb"] == 256
    assert node["resource_disk_gb"] == 5
    assert node["resource_source"] == "default"


def test_estimate_topology_with_replicas():
    topo = _topology(
        _node(
            name="worker",
            config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 3, "node_role": "workload"},
        ),
    )
    estimate = placement_svc.build_resource_estimate(topo)  # type: ignore[arg-type]
    assert estimate["total_replicas"] == 3
    assert estimate["placement_unit_count"] == 3
    assert estimate["total_cpu"] == 1.5
    assert estimate["total_memory_mb"] == 1536


def test_bin_pack_nodes_across_multiple_hosts():
    topo = _topology(
        _node(name="a", config={"resource_cpu": 1, "resource_memory_mb": 3000, "replicas": 1}),
        _node(name="b", config={"resource_cpu": 1, "resource_memory_mb": 3000, "replicas": 1}),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-medium")  # type: ignore[arg-type]
    assert plan["recommended_host_count"] >= 2
    assert len(plan["hosts"]) >= 2
    assigned = [name for host in plan["hosts"] for name in host["assigned_nodes"]]
    assert "a" in assigned
    assert "b" in assigned


def test_nested_resources_can_force_multi_host_placement():
    topo = _topology(
        _node(name="heavy-a", config={"resources": {"cpu": 1, "memory_mb": 900, "disk_gb": 5, "replicas": 1}}),
        _node(name="heavy-b", config={"resources": {"cpu": 1, "memory_mb": 900, "disk_gb": 5, "replicas": 1}}),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    assert plan["recommended_host_count"] == 2
    assert len(plan["hosts"]) == 2


def test_single_host_placement_includes_capacity_fields():
    topo = _topology(
        _node(name="cli-edge", config={"resource_cpu": 0.25, "resource_memory_mb": 256, "replicas": 1}),
        _node(name="svc-origin", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    assert plan["recommended_host_count"] == 1
    host = plan["hosts"][0]
    assert host["host_index"] == 1
    assert host["cpu_capacity"] == 2
    assert host["memory_capacity_mb"] == 1024
    assert set(host["assigned_nodes"]) == {"cli-edge", "svc-origin"}
    assert host["cpu_used"] == 0.75
    assert host["memory_used_mb"] == 768
    assert host["disk_used_gb"] == 10
    assert host["disk_capacity_gb"] == 30


def test_capacity_warning_when_machine_type_too_small():
    topo = _topology(
        _node(name="heavy", config={"resource_cpu": 1, "resource_memory_mb": 900, "replicas": 1}),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    assert any("exceed memory capacity" in w for w in plan["warnings"])


def test_placement_summary_in_generate_payload():
    topo = _topology(_node(name="app", config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}))
    draft = placement_svc.build_generate_deployment_payload(topo)  # type: ignore[arg-type]
    summary = draft["placement_summary"]
    assert summary["recommended_machine_type"] == draft["variables"]["machine_type"]
    assert summary["recommended_host_count"] >= 1
    assert summary["hosts"][0]["assigned_nodes"]


def test_warn_on_public_ports():
    topo = _topology(
        _node(
            name="api",
            config={
                "resource_cpu": 0.5,
                "resource_memory_mb": 512,
                "exposure": "public",
                "required_ports": [8080],
            },
        ),
    )
    plan = placement_svc.build_placement_plan(topo)  # type: ignore[arg-type]
    assert any("public workload" in w.lower() or "exposed ports" in w.lower() for w in plan["warnings"])
    assert 8080 in plan["exposed_ports"]


def test_warn_on_stateful_storage():
    topo = _topology(
        _node(
            name="db",
            image="postgres:16",
            config={"resource_cpu": 1, "resource_memory_mb": 2048, "stateful": True, "node_role": "database"},
        ),
    )
    plan = placement_svc.build_placement_plan(topo)  # type: ignore[arg-type]
    assert any("stateful workload" in w.lower() for w in plan["warnings"])


def test_warn_on_unsupported_placement_constraints():
    topo = _topology(
        _node(
            name="cache",
            config={
                "resource_cpu": 0.5,
                "resource_memory_mb": 512,
                "placement_constraints": ["same_host"],
            },
        ),
    )
    plan = placement_svc.build_placement_plan(topo)  # type: ignore[arg-type]
    assert any("legacy placement constraints" in w.lower() for w in plan["warnings"])


def test_first_fit_best_fit_and_balanced_modes():
    topo = _topology(
        _node(name="a", config={"resource_cpu": 1, "resource_memory_mb": 512, "resource_disk_gb": 5}),
        _node(name="b", config={"resource_cpu": 1, "resource_memory_mb": 512, "resource_disk_gb": 5}),
        _node(name="c", config={"resource_cpu": 1, "resource_memory_mb": 512, "resource_disk_gb": 5}),
    )
    first = placement_svc.build_placement_plan(topo, machine_type="e2-small", placement_mode="first_fit")  # type: ignore[arg-type]
    best = placement_svc.build_placement_plan(topo, machine_type="e2-small", placement_mode="best_fit")  # type: ignore[arg-type]
    balanced = placement_svc.build_placement_plan(
        topo,
        machine_type="e2-small",
        host_count=3,
        placement_mode="balanced",
    )  # type: ignore[arg-type]
    assert first["placement_mode"] == "first_fit"
    assert best["placement_mode"] == "best_fit"
    assert balanced["placement_mode"] == "balanced"
    assert balanced["recommended_host_count"] == 3
    assert all("utilization" in host for host in balanced["hosts"])


def test_different_host_constraint_splits_nodes():
    topo = _topology(
        _node(name="worker-a", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
        _node(name="worker-b", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
    )
    plan = placement_svc.build_placement_plan(
        topo,
        machine_type="e2-micro",
        constraints=[
            {"constraint_type": "different_host", "node_a": "worker-a", "node_b": "worker-b"}
        ],
    )  # type: ignore[arg-type]
    host_by_node = {
        detail["node_name"]: host["host_index"]
        for host in plan["hosts"]
        for detail in host.get("assigned_node_details") or []
    }
    assert host_by_node["worker-a"] != host_by_node["worker-b"]
    assert plan["recommended_host_count"] == 2


def test_small_topology_returns_one_host_without_constraints():
    topo = _topology(
        _node(name="cli-edge", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
        _node(name="svc-origin", config={"resource_cpu": 0.5, "resource_memory_mb": 512}),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    assert plan["recommended_host_count"] == 1


def test_same_host_constraint_keeps_nodes_together():
    topo = _topology(
        _node(name="worker-a", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
        _node(name="worker-b", config={"resource_cpu": 0.25, "resource_memory_mb": 256}),
    )
    plan = placement_svc.build_placement_plan(
        topo,
        machine_type="e2-micro",
        constraints=[{"constraint_type": "same_host", "node_a": "worker-a", "node_b": "worker-b"}],
    )  # type: ignore[arg-type]
    host_by_node = {
        detail["node_name"]: host["host_index"]
        for host in plan["hosts"]
        for detail in host.get("assigned_node_details") or []
    }
    assert host_by_node["worker-a"] == host_by_node["worker-b"]


def test_impossible_same_host_constraint_warns():
    topo = _topology(
        _node(name="heavy-a", config={"resource_cpu": 1.5, "resource_memory_mb": 800}),
        _node(name="heavy-b", config={"resource_cpu": 1.5, "resource_memory_mb": 800}),
    )
    plan = placement_svc.build_placement_plan(
        topo,
        machine_type="e2-micro",
        constraints=[{"constraint_type": "same_host", "node_a": "heavy-a", "node_b": "heavy-b"}],
    )  # type: ignore[arg-type]
    assert any("same_host constraint could not be satisfied" in warning for warning in plan["warnings"])


def test_generate_payload_uses_placement_recommendation():
    topo = _topology(_node(config={"resource_cpu": 0.5, "resource_memory_mb": 512, "replicas": 1}))
    draft = placement_svc.build_generate_deployment_payload(topo)  # type: ignore[arg-type]
    assert draft["variables"]["machine_type"] in {"e2-micro", "e2-small", "e2-medium"}
    assert draft["variables"]["vm_count"] == 1
    assert draft["placement_plan"]["recommended_machine_type"] == draft["variables"]["machine_type"]


def test_resource_metadata_validates_node_role_and_exposure():
    with pytest.raises(NodeConfigValidationError):
        validate_and_normalize_node_config({"node_role": "invalid-role"})
    with pytest.raises(NodeConfigValidationError):
        validate_and_normalize_node_config({"exposure": "internet"})

    cfg = validate_and_normalize_node_config(
        {
            "resource_cpu": 1,
            "resource_memory_mb": 1024,
            "resource_disk_gb": 10,
            "replicas": 2,
            "node_role": "database",
            "exposure": "private",
            "stateful": True,
            "required_ports": [5432],
            "notes": "primary db",
        }
    )
    assert cfg is not None
    assert cfg["node_role"] == "database"
    assert cfg["exposure"] == "private"


def test_legacy_cpu_request_alias():
    cfg = validate_and_normalize_node_config({"cpu_request": 2, "memory_request_mb": 4096, "disk_request_gb": 20})
    assert cfg is not None
    topo = _topology(_node(config=cfg))
    estimate = placement_svc.build_resource_estimate(topo)  # type: ignore[arg-type]
    assert estimate["total_cpu"] == 2.0
    assert estimate["total_memory_mb"] == 4096


def test_node_role_enum_values():
    assert "workload" in NODE_ROLES
    assert "database" in NODE_ROLES
    assert "public" in EXPOSURE_VALUES


def test_estimate_response_includes_cpu_aliases():
    from app.api.topology_placement import _estimate_response

    payload = _estimate_response(
        {
            "total_cpu": 1.0,
            "total_memory_mb": 1024,
            "total_disk_gb": 8.0,
            "total_replicas": 1,
            "node_count": 1,
            "workload_node_count": 1,
            "placement_unit_count": 1,
            "nodes": [
                {
                    "node_id": "n1",
                    "node_name": "app",
                    "resource_cpu": 1.0,
                    "resource_memory_mb": 1024,
                    "resource_disk_gb": 8.0,
                    "replicas": 1,
                    "resource_source": "explicit",
                    "node_role": "workload",
                    "exposure": "internal",
                    "stateful": False,
                }
            ],
        }
    )
    dumped = payload.model_dump()
    node = dumped["nodes"][0]
    assert node["cpu"] == 1.0
    assert node["memory_mb"] == 1024
    assert node["disk_gb"] == 8.0
    assert node["resource_source"] == "explicit"


def _placement_test_headers(client_strict):
    email = f"place{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Place"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "placement-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    assert topo.status_code == 201, topo.text
    return headers, topo.json()["id"]


def _add_workload_node(client_strict, *, headers, topo_id: str, name: str, cpu: float, memory_mb: int):
    node = client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={
            "name": name,
            "node_type": "host",
            "image": "nginx:latest",
            "config": {
                "resource_cpu": cpu,
                "resource_memory_mb": memory_mb,
                "resource_disk_gb": 5,
                "replicas": 1,
            },
        },
    )
    assert node.status_code == 201, node.text


def test_placement_constraint_crud_and_plan_host_count(client_strict, engine_db):
    headers, topo_id = _placement_test_headers(client_strict)
    _add_workload_node(client_strict, headers=headers, topo_id=topo_id, name="cli-edge", cpu=0.25, memory_mb=256)
    _add_workload_node(client_strict, headers=headers, topo_id=topo_id, name="svc-origin", cpu=0.5, memory_mb=512)

    listed = client_strict.get(f"/topologies/{topo_id}/placement-constraints", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []

    baseline_plan = client_strict.get(f"/topologies/{topo_id}/placement-plan", headers=headers)
    assert baseline_plan.status_code == 200, baseline_plan.text
    assert baseline_plan.json()["recommended_host_count"] == 1

    baseline_strategy = client_strict.get(f"/topologies/{topo_id}/strategy-recommendation", headers=headers)
    assert baseline_strategy.status_code == 200, baseline_strategy.text
    assert baseline_strategy.json()["recommended_strategy"] == "docker-vm"

    created = client_strict.post(
        f"/topologies/{topo_id}/placement-constraints",
        headers=headers,
        json={
            "constraint_type": "different_host",
            "node_a": "cli-edge",
            "node_b": "svc-origin",
        },
    )
    assert created.status_code == 201, created.text
    constraint_id = created.json()["id"]
    assert created.json()["constraint_type"] == "different_host"

    listed_after_create = client_strict.get(f"/topologies/{topo_id}/placement-constraints", headers=headers)
    assert listed_after_create.status_code == 200, listed_after_create.text
    assert len(listed_after_create.json()["items"]) == 1
    assert listed_after_create.json()["items"][0]["node_a"] == "cli-edge"
    assert listed_after_create.json()["items"][0]["node_b"] == "svc-origin"

    constrained_plan = client_strict.get(f"/topologies/{topo_id}/placement-plan", headers=headers)
    assert constrained_plan.status_code == 200, constrained_plan.text
    assert constrained_plan.json()["recommended_host_count"] == 2

    constrained_strategy = client_strict.get(f"/topologies/{topo_id}/strategy-recommendation", headers=headers)
    assert constrained_strategy.status_code == 200, constrained_strategy.text
    assert constrained_strategy.json()["recommended_strategy"] == "docker-multi-vm"

    deleted = client_strict.delete(
        f"/topologies/{topo_id}/placement-constraints/{constraint_id}",
        headers=headers,
    )
    assert deleted.status_code == 204, deleted.text

    listed_after_delete = client_strict.get(f"/topologies/{topo_id}/placement-constraints", headers=headers)
    assert listed_after_delete.status_code == 200, listed_after_delete.text
    assert listed_after_delete.json()["items"] == []

    restored_plan = client_strict.get(f"/topologies/{topo_id}/placement-plan", headers=headers)
    assert restored_plan.status_code == 200, restored_plan.text
    assert restored_plan.json()["recommended_host_count"] == 1

    restored_strategy = client_strict.get(f"/topologies/{topo_id}/strategy-recommendation", headers=headers)
    assert restored_strategy.status_code == 200, restored_strategy.text
    assert restored_strategy.json()["recommended_strategy"] == "docker-vm"


def test_delete_placement_constraint_returns_404_for_unknown_id(client_strict, engine_db):
    headers, topo_id = _placement_test_headers(client_strict)
    missing = client_strict.delete(
        f"/topologies/{topo_id}/placement-constraints/{uuid.uuid4()}",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text


def test_placement_plan_api(client_strict, engine_db):
    email = f"place{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Place"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "placement-lab",
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
            "name": "redis",
            "node_type": "generic",
            "image": "redis:7",
            "config": {
                "resource_cpu": 0.5,
                "resource_memory_mb": 1024,
                "node_role": "cache",
                "exposure": "internal",
            },
        },
    )
    assert node.status_code == 201, node.text

    plan = client_strict.get(f"/topologies/{topo_id}/placement-plan", headers=headers)
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["total_memory_mb"] >= 1024
    assert body["recommended_machine_type"]
    assert len(body["hosts"]) >= 1
    assert body["hosts"][0]["assigned_nodes"][0] == "redis"
    assert body["hosts"][0]["host_index"] == 1
    assert body["hosts"][0]["cpu_capacity"] > 0
    assert body["hosts"][0]["memory_capacity_mb"] > 0
    assert body["hosts"][0]["disk_capacity_gb"] == 30
    assert body["nodes"][0]["node_name"] == "redis"
    assert body["nodes"][0]["cpu"] == body["nodes"][0]["resource_cpu"]


def test_generate_infrastructure_deployment_uses_credential_profile_project_id(
    client_strict, monkeypatch, engine_db, tmp_path
):
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    email = f"genplace{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "GenPlace"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]

    profile = client_strict.post(
        f"/projects/{project_id}/credential-profiles",
        headers=headers,
        json={
            "name": "GCP",
            "provider": "gcp",
            "credential_type": "gcp_service_account_json",
            "secret": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "my-gcp-project",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
                    "client_email": "demo@test.iam.gserviceaccount.com",
                }
            ),
        },
    )
    cred_ref = profile.json()["credentials_ref"]

    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "gen-place-lab",
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
        json={"provider": "gcp", "credentials_ref": cred_ref},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["deployment"]["variables_json"]["project_id"] == "my-gcp-project"
    assert body["placement_plan"]["recommended_machine_type"]
    assert body["placement_plan"]["hosts"]


def test_generate_missing_gcp_project_id_on_profile(client_strict, monkeypatch, engine_db, tmp_path):
    from app.core.credential_encryption import encrypt_secret
    from app.db.session import SessionLocal
    from app.models.credential_profile import CredentialProfile
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    email = f"misspid{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "MissPid"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]

    profile_id = uuid.uuid4()
    with SessionLocal() as db:
        from sqlalchemy import select

        from app.models.user import User

        user = db.scalar(select(User).where(User.email == email))
        db.add(
            CredentialProfile(
                id=profile_id,
                project_id=uuid.UUID(project_id),
                owner_id=user.id,
                name="Missing GCP project",
                gcp_project_id=None,
                provider="gcp",
                credential_type="gcp_service_account_json",
                encrypted_secret=encrypt_secret(
                    json.dumps(
                        {
                            "type": "service_account",
                            "project_id": "my-gcp-project",
                            "private_key": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
                            "client_email": "demo@test.iam.gserviceaccount.com",
                        }
                    )
                ),
                metadata_json={},
                validation_status="valid",
            )
        )
        db.commit()

    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "miss-pid-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={"name": "web", "node_type": "host", "image": "nginx", "config": {"resource_memory_mb": 512}},
    )

    generated = client_strict.post(
        f"/topologies/{topo_id}/generate-infrastructure-deployment",
        headers=headers,
        json={"provider": "gcp", "credentials_ref": f"credential:{profile_id}"},
    )
    assert generated.status_code == 400, generated.text
    assert "Selected credential profile does not contain a GCP project ID." in generated.text
