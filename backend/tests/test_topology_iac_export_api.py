"""Step 52A: topology IaC export API."""

from __future__ import annotations

import io
import uuid
import zipfile

from app.models.topology import NodeType

TOPO = {
    "name": "iac-export-lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_with_node(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "api",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "config": {
                "command": "nginx -g 'daemon off;'",
                "ports": [{"port": 80, "target_port": 80}],
                "role_label": "web",
            },
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": n["id"],
            "target_node_id": n["id"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    return tid


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "IAC"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_preview_endpoint_works(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["topology_id"] == tid
    assert len(body["artifacts"]) == 5
    assert "docker-compose" in body["previews"]
    assert "kubernetes" in body["previews"]
    assert set(body["terraform_files"]) == {"main.tf", "variables.tf", "outputs.tf", "README.md"}
    assert "inventory.ini" in body["ansible_files"]
    assert any(w["code"] == "custom_command_included" for w in body["warnings"])


def test_preview_warnings_for_incomplete_node(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "blank",
            "node_type": NodeType.HOST.value,
            "image": None,
            "config": None,
        },
    )
    body = client.get(f"/topologies/{tid}/exports/preview").json()
    codes = {w["code"] for w in body["warnings"]}
    assert "missing_image" in codes
    assert "no_ports_configured" in codes


def test_docker_compose_export_returns_yaml(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/docker-compose")
    assert r.status_code == 200
    assert "yaml" in r.headers.get("content-type", "")
    assert 'attachment; filename="docker-compose.cns.yml"' in r.headers.get("content-disposition", "")
    assert b"services:" in r.content
    assert b"nginx:alpine" in r.content


def test_kubernetes_export_returns_yaml(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/kubernetes")
    assert r.status_code == 200
    assert b"kind: Deployment" in r.content
    assert 'attachment; filename="kubernetes.cns.yaml"' in r.headers.get("content-disposition", "")


def test_terraform_export_returns_zip(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/terraform")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert {"main.tf", "variables.tf", "outputs.tf", "README.md"} <= set(zf.namelist())


def test_ansible_export_returns_zip(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/ansible")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert {"inventory.ini", "playbook.yml", "README.md"} <= set(zf.namelist())


def test_archive_export_contains_all_artifacts(client):
    tid = _topology_with_node(client)
    r = client.get(f"/topologies/{tid}/exports/archive")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    assert "docker-compose.cns.yml" in names
    assert "kubernetes.cns.yaml" in names
    assert "terraform/main.tf" in names
    assert "ansible/playbook.yml" in names


def test_unauthorized_user_blocked(client_strict):
    _, owner_h = _reg(client_strict, "iaco")
    _, other_h = _reg(client_strict, "iacx")
    pid = client_strict.get("/projects", headers=owner_h).json()[0]["id"]
    tid = client_strict.post(
        "/topologies",
        headers=owner_h,
        json={**TOPO, "project_id": pid},
    ).json()["id"]
    r = client_strict.get(f"/topologies/{tid}/exports/docker-compose", headers=other_h)
    assert r.status_code == 404
