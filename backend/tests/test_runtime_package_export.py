"""Tests for runtime package export (Step 65)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from app.services import runtime_package_export_service as package_svc


def _register_and_headers(client_strict):
    email = f"pkg{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Pkg"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    return headers, project_id


def _create_topology_with_nodes(
    client_strict,
    headers,
    project_id,
    *,
    nodes: list[dict] | None = None,
    constraints: list[dict] | None = None,
):
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "runtime-pkg-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    default_nodes = [
        {
            "name": "cli-edge",
            "node_type": "host",
            "image": "alpine:latest",
            "config": {"resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
        },
        {
            "name": "svc-origin",
            "node_type": "host",
            "image": "nginx:alpine",
            "config": {
                "resource_cpu": 0.5,
                "resource_memory_mb": 512,
                "resource_disk_gb": 8,
                "health_check": {"check_type": "http", "port": 80, "path": "/"},
            },
        },
    ]
    for node in nodes or default_nodes:
        client_strict.post(f"/topologies/{topo_id}/nodes", headers=headers, json=node)
    for constraint in constraints or []:
        client_strict.post(f"/topologies/{topo_id}/placement-constraints", headers=headers, json=constraint)
    return topo_id


def _read_zip_member(payload: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        return zf.read(name).decode("utf-8")


def test_generate_docker_vm_runtime_package(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(client_strict, headers, project_id)

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-vm", "provider": "gcp", "machine_type": "e2-micro"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["strategy_id"] == "docker-vm"
    assert body["status"] == "generated"
    assert body["planning_only"] is False
    assert "docker-compose.yml" in body["files"]
    assert ".env.example" in body["files"]
    assert "deployment-manifest.json" in body["files"]
    assert "host-placement.json" in body["files"]
    assert "README.md" in body["files"]
    assert body["download_url"].startswith("/api/runtime-packages/")
    assert body["download_url"].endswith("/download")

    package_id = body["package_id"]
    download = client_strict.get(f"/runtime-packages/{package_id}/download", headers=headers)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("application/zip")

    compose = _read_zip_member(download.content, "docker-compose.yml")
    assert "cli-edge:" in compose
    assert "svc-origin:" in compose
    assert "image: alpine:latest" in compose
    assert "image: nginx:alpine" in compose
    assert "healthcheck:" in compose
    assert "cns-net:" in compose
    assert "10.50.0.0/24" in compose

    manifest = json.loads(_read_zip_member(download.content, "deployment-manifest.json"))
    assert manifest["topology_id"] == topo_id
    assert manifest["strategy_id"] == "docker-vm"
    assert manifest["placement_plan"]["recommended_host_count"] == 1
    assert manifest["cost_estimate"]["cost_estimate"]

    host_placement = json.loads(_read_zip_member(download.content, "host-placement.json"))
    assert host_placement["host_count"] == 1
    assert host_placement["hosts"]
    assigned = host_placement["hosts"][0]["assigned_nodes"]
    assert "cli-edge" in assigned
    assert "svc-origin" in assigned


def test_docker_compose_includes_public_ports_only(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(
        client_strict,
        headers,
        project_id,
        nodes=[
            {
                "name": "public-api",
                "node_type": "host",
                "image": "nginx:alpine",
                "config": {
                    "resource_cpu": 0.5,
                    "resource_memory_mb": 512,
                    "resource_disk_gb": 5,
                    "exposure": "public",
                    "required_ports": [8080],
                },
            },
            {
                "name": "internal-db",
                "node_type": "host",
                "image": "postgres:16",
                "config": {
                    "resource_cpu": 0.5,
                    "resource_memory_mb": 512,
                    "resource_disk_gb": 10,
                    "exposure": "internal",
                    "required_ports": [5432],
                },
            },
        ],
    )

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-vm", "provider": "gcp"},
    )
    assert response.status_code == 201, response.text
    package_id = response.json()["package_id"]
    download = client_strict.get(f"/runtime-packages/{package_id}/download", headers=headers)
    compose = _read_zip_member(download.content, "docker-compose.yml")
    assert '"8080:8080"' in compose
    # Internal workloads may reference ports in healthchecks; only public exposure publishes host ports.
    assert '"5432:5432"' not in compose


def test_planning_only_strategy_package_marks_limitations(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(
        client_strict,
        headers,
        project_id,
        constraints=[
            {"constraint_type": "different_host", "node_a": "cli-edge", "node_b": "svc-origin"},
        ],
    )

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-multi-vm", "provider": "gcp", "machine_type": "e2-micro"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "planning_only"
    assert body["planning_only"] is True
    assert "docker-compose.yml" not in body["files"]
    assert "host-placement.json" in body["files"]
    assert "README.md" in body["files"]
    assert body["limitations"]

    package_id = body["package_id"]
    download = client_strict.get(f"/runtime-packages/{package_id}/download", headers=headers)
    readme = _read_zip_member(download.content, "README.md")
    assert "not directly runnable" in readme.lower()
    manifest = json.loads(_read_zip_member(download.content, "deployment-manifest.json"))
    assert manifest["planning_only"] is True


def test_k8s_cluster_planning_package(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(client_strict, headers, project_id)

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "k8s-cluster", "provider": "gcp"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["planning_only"] is True
    assert "manifest-summary.json" in body["files"]
    assert "README.md" in body["files"]
    assert "docker-compose.yml" not in body["files"]


def test_invalid_topology_returns_validation_error(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "empty-topology",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-vm", "provider": "gcp"},
    )
    assert response.status_code == 400
    assert "at least one node" in response.json()["detail"].lower()


def test_missing_images_returns_validation_error(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(
        client_strict,
        headers,
        project_id,
        nodes=[
            {
                "name": "no-image",
                "node_type": "host",
                "config": {"resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
            },
        ],
    )

    response = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-vm", "provider": "gcp"},
    )
    assert response.status_code == 400
    assert "images" in response.json()["detail"].lower()


def test_docker_compose_uses_configurable_runtime_subnet_unit():
    from types import SimpleNamespace

    topo = SimpleNamespace(
        id=uuid.uuid4(),
        name="subnet-lab",
        nodes=[
            SimpleNamespace(
                id=uuid.uuid4(),
                name="web",
                node_type=SimpleNamespace(value="host"),
                image="nginx:alpine",
                ip_address=None,
                config={"resource_cpu": 0.5, "resource_memory_mb": 512, "resource_disk_gb": 5},
            ),
        ],
        links=[],
    )
    compose = package_svc.generate_docker_compose(topo)  # type: ignore[arg-type]
    assert "${CNS_RUNTIME_SUBNET:-10.250.0.0/24}" in compose
    assert "10.50.0.0/24" not in compose
    assert "10.250.0.10" in compose


def test_compose_service_name_sanitization_unit():
    from types import SimpleNamespace

    node = SimpleNamespace(id=uuid.uuid4(), name="My Service #1")
    names = package_svc._unique_service_names([node])
    assert names[node.id] == "my-service-1"


def test_ip_conflict_validation_unit():
    from types import SimpleNamespace

    topo = SimpleNamespace(
        nodes=[
            SimpleNamespace(name="a", ip_address="10.50.0.10"),
            SimpleNamespace(name="b", ip_address="10.50.0.10"),
        ]
    )
    with pytest.raises(ValueError, match="Duplicate IP"):
        package_svc._validate_ip_addresses(topo)
