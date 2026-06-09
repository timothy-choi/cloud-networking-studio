"""Tests for runtime package import / rehydrate (Step 66)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from app.services import runtime_package_import_service as import_svc


def _register_and_headers(client_strict):
    email = f"import{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Import"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    return headers, project_id


def _create_topology_with_nodes(client_strict, headers, project_id):
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "import-source-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    topo_id = topo.json()["id"]
    for node in [
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
    ]:
        client_strict.post(f"/topologies/{topo_id}/nodes", headers=headers, json=node)
    return topo_id


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_export_import_round_trip(client_strict, monkeypatch, engine_db, tmp_path):
    from tests.test_infrastructure_deployments_57e import _gcp_credentials, _patch_gcp_ssh_gates

    _patch_gcp_ssh_gates(monkeypatch)
    _gcp_credentials(monkeypatch, tmp_path)

    headers, project_id = _register_and_headers(client_strict)
    topo_id = _create_topology_with_nodes(client_strict, headers, project_id)

    generated = client_strict.post(
        f"/topologies/{topo_id}/runtime-package",
        headers=headers,
        json={"strategy_id": "docker-vm", "provider": "gcp", "machine_type": "e2-micro"},
    )
    assert generated.status_code == 201, generated.text
    package_id = generated.json()["package_id"]
    download = client_strict.get(f"/runtime-packages/{package_id}/download", headers=headers)
    assert download.status_code == 200

    files = {"file": ("runtime-package.zip", download.content, "application/zip")}
    imported = client_strict.post(
        "/runtime-packages/import",
        headers=headers,
        data={"project_id": project_id},
        files=files,
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["node_count"] == 2
    assert body["strategy_id"] == "docker-vm"
    assert body["placement_plan_id"]
    assert ".env.example" in body["files_imported"]

    new_topo_id = body["topology_id"]
    nodes = client_strict.get(f"/topologies/{new_topo_id}/nodes", headers=headers)
    assert nodes.status_code == 200
    node_names = {row["name"] for row in nodes.json()}
    assert node_names == {"cli-edge", "svc-origin"}

    plan = client_strict.get(f"/topologies/{new_topo_id}/placement-plan", headers=headers)
    assert plan.status_code == 200
    assert plan.json()["workload_node_count"] == 2

    topo = client_strict.get(f"/topologies/{new_topo_id}", headers=headers).json()
    assert topo["name"].endswith("(imported)")

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
    assert profile.status_code == 201, profile.text
    cred_ref = profile.json()["credentials_ref"]

    generated_infra = client_strict.post(
        f"/topologies/{new_topo_id}/generate-infrastructure-deployment",
        headers=headers,
        json={
            "provider": "gcp",
            "machine_type": "e2-micro",
            "template_id": "docker-vm",
            "credentials_ref": cred_ref,
        },
    )
    assert generated_infra.status_code == 201, generated_infra.text
    infra_body = generated_infra.json()
    assert infra_body["deployment"]["name"].endswith("(imported)-infra")
    assert infra_body["deployment"]["variables_json"]["deployment_name"] == "import-source-lab-imported"
    assert infra_body["deployment"]["variables_json"]["instance_name"].startswith("cns-")
    assert infra_body["deployment"]["variables_json"]["project_id"] == "my-gcp-project"


def test_import_rejects_missing_manifest(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    payload = _zip_bytes({"README.md": "# hello"})
    response = client_strict.post(
        "/runtime-packages/import",
        headers=headers,
        data={"project_id": project_id},
        files={"file": ("bad.zip", payload, "application/zip")},
    )
    assert response.status_code == 400
    assert "deployment-manifest.json" in response.json()["detail"].lower()


def test_import_rejects_unsafe_zip_paths(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../deployment-manifest.json", "{}")
    response = client_strict.post(
        "/runtime-packages/import",
        headers=headers,
        data={"project_id": project_id},
        files={"file": ("bad.zip", buf.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert "unsafe" in response.json()["detail"].lower()


def test_import_rejects_invalid_compose(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    manifest = {
        "topology_name": "broken",
        "strategy_id": "docker-vm",
        "link_count": 0,
        "placement_plan": {
            "nodes": [{"node_name": "web", "resource_cpu": 0.5, "resource_memory_mb": 512, "resource_disk_gb": 5}],
        },
    }
    payload = _zip_bytes(
        {
            "deployment-manifest.json": json.dumps(manifest),
            "host-placement.json": json.dumps({"hosts": [], "placement_constraints": []}),
            "docker-compose.yml": "not valid compose",
        }
    )
    response = client_strict.post(
        "/runtime-packages/import",
        headers=headers,
        data={"project_id": project_id},
        files={"file": ("bad.zip", payload, "application/zip")},
    )
    assert response.status_code == 400
    assert "services" in response.json()["detail"].lower()


def test_parse_docker_compose_extracts_services():
    compose = """# Generated
services:
  cli-edge:
    image: alpine:latest
    networks:
      cns-net:
        ipv4_address: 10.250.0.10
  svc-origin:
    image: nginx:alpine
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:80/"]
      interval: 10s
networks:
  cns-net:
    driver: bridge
    ipam:
      config:
        - subnet: ${CNS_RUNTIME_SUBNET:-10.250.0.0/24}
"""
    parsed = import_svc.parse_docker_compose(compose)
    assert "cli-edge" in parsed.services
    assert parsed.services["cli-edge"].image == "alpine:latest"
    assert parsed.services["cli-edge"].ipv4_address == "10.250.0.10"
    assert parsed.services["svc-origin"].ports == [8080]
    assert parsed.services["svc-origin"].health_check == {"check_type": "http", "port": 80, "path": "/"}


def test_planning_only_package_import_without_compose(client_strict, engine_db):
    headers, project_id = _register_and_headers(client_strict)
    manifest = {
        "topology_name": "planning-only",
        "strategy_id": "docker-multi-vm",
        "link_count": 0,
        "planning_only": True,
        "placement_plan": {
            "nodes": [
                {"node_name": "worker-a", "resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
                {"node_name": "worker-b", "resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
            ],
            "hosts": [
                {
                    "host_index": 1,
                    "assigned_nodes": ["worker-a"],
                    "assigned_node_details": [
                        {"node_name": "worker-a", "resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
                    ],
                },
                {
                    "host_index": 2,
                    "assigned_nodes": ["worker-b"],
                    "assigned_node_details": [
                        {"node_name": "worker-b", "resource_cpu": 0.25, "resource_memory_mb": 256, "resource_disk_gb": 5},
                    ],
                },
            ],
        },
    }
    payload = _zip_bytes(
        {
            "deployment-manifest.json": json.dumps(manifest),
            "host-placement.json": json.dumps(
                {
                    "host_count": 2,
                    "placement_constraints": [
                        {"constraint_type": "different_host", "node_a": "worker-a", "node_b": "worker-b"},
                    ],
                }
            ),
            "README.md": "# planning only",
        }
    )
    response = client_strict.post(
        "/runtime-packages/import",
        headers=headers,
        data={"project_id": project_id},
        files={"file": ("planning.zip", payload, "application/zip")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["planning_only"] is True
    assert body["node_count"] == 2
    constraints = client_strict.get(
        f"/topologies/{body['topology_id']}/placement-constraints",
        headers=headers,
    )
    assert constraints.status_code == 200
    assert len(constraints.json()["items"]) == 1
