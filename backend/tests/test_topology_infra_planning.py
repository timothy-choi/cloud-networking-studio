"""Tests for topology-aware infrastructure planning (Feature 58B)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.topology import NodeType
from app.services import topology_infra_planning_service as planning_svc


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
    return SimpleNamespace(nodes=list(nodes), name="lab-topology", id=uuid.uuid4())


def test_estimate_topology_resources_sums_node_requests():
    topo = _topology(
        _node(name="web", config={"cpu_request": 1, "memory_request_mb": 1024, "disk_request_gb": 10, "replicas": 2}),
        _node(name="db", image="postgres:16", config={"replicas": 1}),
        _node(name="core-switch", node_type=NodeType.SWITCH),
    )
    estimate = planning_svc.estimate_topology_resources(topo)  # type: ignore[arg-type]
    assert estimate["node_count"] == 3
    assert estimate["workload_node_count"] == 2
    assert estimate["total_cpu"] == 3.0
    assert estimate["total_memory_mb"] == 4096
    assert estimate["total_replicas"] == 3


def test_recommendations_include_cloud_providers():
    topo = _topology(_node(config={"cpu_request": 2, "memory_request_mb": 8192, "disk_request_gb": 20, "replicas": 1}))
    recs = planning_svc.build_infrastructure_recommendations(topo)  # type: ignore[arg-type]
    assert "e2-standard-2" in recs["recommendations"]["gcp"]
    assert "t3.large" in recs["recommendations"]["aws"]
    assert "Standard_B2ms" in recs["recommendations"]["azure"]
    assert recs["suggested_template_id"] == "docker-vm"
    assert recs["suggested_variables"]["machine_type"] in {"e2-micro", "e2-small", "e2-medium"}


def test_capacity_validation_insufficient_memory():
    topo = _topology(_node(config={"cpu_request": 1, "memory_request_mb": 8192, "replicas": 1}))
    result = planning_svc.validate_topology_capacity(
        topo,  # type: ignore[arg-type]
        provider="gcp",
        variables={"machine_type": "e2-micro", "vm_count": 1},
    )
    assert result["status"] == "insufficient_capacity"
    assert any("8192" in msg and "1024" in msg for msg in result["messages"])


def test_capacity_validation_compatible():
    topo = _topology(_node(config={"cpu_request": 0.5, "memory_request_mb": 512, "replicas": 1}))
    result = planning_svc.validate_topology_capacity(
        topo,  # type: ignore[arg-type]
        provider="gcp",
        variables={"machine_type": "e2-medium", "vm_count": 1},
    )
    assert result["status"] == "compatible"


def test_generate_payload_clamps_gcp_machine_type():
    topo = _topology(_node(config={"cpu_request": 0.25, "memory_request_mb": 256, "replicas": 1}))
    draft = planning_svc.build_generate_deployment_payload(topo)  # type: ignore[arg-type]
    assert draft["provider"] == "gcp"
    assert draft["template_id"] == "docker-vm"
    assert draft["variables"]["machine_type"] in {"e2-micro", "e2-small", "e2-medium"}
    assert draft["capacity_check"]["status"] in {"compatible", "warning"}


def test_resource_fields_validate_on_node_config():
    from app.services.node_runtime_config import NodeConfigValidationError, validate_and_normalize_node_config

    cfg = validate_and_normalize_node_config(
        {"cpu_request": 1, "memory_request_mb": 1024, "disk_request_gb": 10, "replicas": 2}
    )
    assert cfg is not None
    assert cfg["cpu_request"] == 1
    assert cfg["memory_request_mb"] == 1024

    with pytest.raises(NodeConfigValidationError):
        validate_and_normalize_node_config({"memory_request_mb": 10})


def test_resource_estimate_api_returns_node_fields(client_strict, engine_db):
    email = f"est{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Est"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "estimate-lab",
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
            "image": "nginx:latest",
            "config": {"resource_cpu": 1, "resource_memory_mb": 1024, "resource_disk_gb": 8, "replicas": 1},
        },
    )
    assert node.status_code == 201, node.text

    estimate = client_strict.get(f"/topologies/{topo_id}/resource-estimate", headers=headers)
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["total_cpu"] >= 1
    assert body["total_memory_mb"] >= 1024
    assert body["node_count"] == 1
    assert body["nodes"][0]["node_name"] == "app"
    assert body["nodes"][0]["cpu"] == 1
    assert body["nodes"][0]["memory_mb"] == 1024
    assert body["nodes"][0]["disk_gb"] == 8
    assert body["nodes"][0]["replicas"] == 1


def test_infrastructure_recommendations_api(client_strict, engine_db):
    email = f"rec{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Rec"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "rec-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={"name": "svc", "node_type": "generic", "image": "redis:7", "config": {}},
    )
    recs = client_strict.get(f"/topologies/{topo_id}/infrastructure-recommendations", headers=headers)
    assert recs.status_code == 200, recs.text
    payload = recs.json()
    assert "gcp" in payload["recommendations"]
    assert payload["suggested_template_id"] == "docker-vm"


def test_generate_infrastructure_deployment_api(client_strict, monkeypatch, engine_db, tmp_path):
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    email = f"gen{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Gen"},
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
            "name": "gen-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={"name": "web", "node_type": "host", "image": "nginx", "config": {"memory_request_mb": 512}},
    )

    generated = client_strict.post(
        f"/topologies/{topo_id}/generate-infrastructure-deployment",
        headers=headers,
        json={
            "provider": "gcp",
            "credentials_ref": cred_ref,
            "variables": {"zone": "us-central1-a"},
        },
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["deployment"]["topology_id"] == topo_id
    assert body["deployment"]["template_id"] == "docker-vm"
    assert body["deployment"]["variables_json"]["project_id"] == "my-gcp-project"
    assert body["capacity_check"]["status"] in {"compatible", "warning"}
    assert body["placement_plan"]["recommended_machine_type"]


def test_generate_infrastructure_deployment_missing_gcp_project_id(
    client_strict, monkeypatch, engine_db, tmp_path
):
    from app.db.session import SessionLocal
    from app.models.credential_profile import CredentialProfile
    from app.core.credential_encryption import encrypt_secret
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    email = f"genmiss{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "GenMiss"},
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

    cred_ref = f"credential:{profile_id}"
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "gen-miss-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={"name": "web", "node_type": "host", "image": "nginx", "config": {"memory_request_mb": 512}},
    )

    generated = client_strict.post(
        f"/topologies/{topo_id}/generate-infrastructure-deployment",
        headers=headers,
        json={"provider": "gcp", "credentials_ref": cred_ref},
    )
    assert generated.status_code == 400, generated.text
    assert "Selected credential profile does not contain a GCP project ID." in generated.text


def test_validate_rejects_undersized_deployment(client_strict, monkeypatch, engine_db, tmp_path):
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    email = f"valcap{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "ValCap"},
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
            "name": "heavy-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={
            "name": "db",
            "node_type": "host",
            "image": "postgres:16",
            "config": {"memory_request_mb": 8192, "cpu_request": 2, "replicas": 1},
        },
    )
    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=headers,
        json={
            "name": "too-small",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": cred_ref,
            "variables": {
                "project_id": "my-gcp-project",
                "region": "us-central1",
                "zone": "us-central1-a",
                "machine_type": "e2-micro",
                "network_name": "default",
                "instance_name": "cns-docker-vm",
                "ssh_user": "ubuntu",
                "allowed_ssh_cidr": "203.0.113.0/24",
                "allowed_app_cidr": "203.0.113.0/24",
                "tags": "cns-docker-vm",
                "vm_count": 1,
            },
        },
    )
    assert create.status_code == 400, create.text
    assert "8192" in create.text or "RAM" in create.text
