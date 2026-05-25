"""Tests for deployment target PATCH and compose export polish."""

from __future__ import annotations

import uuid

from app.services.node_runtime_config import extract_node_runtime_config
from app.services.topology_iac_export_service import (
    ExportNode,
    TopologyExportBundle,
    generate_docker_compose,
)

TOPOLOGY_BODY = {
    "name": "Target Patch Lab",
    "description": "deployment target patch",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client, prefix: str = "dt") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "DT"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _project_id(client, headers) -> str:
    return client.get("/projects", headers=headers).json()[0]["id"]


def _create_target(client, headers, project_id: str, **overrides) -> dict:
    body = {
        "name": "Remote Host",
        "target_type": "remote_docker",
        "config_json": {
            "host": "10.0.0.1",
            "ssh_user": "ubuntu",
            "remote_workdir": "/opt/cns",
            "supports_compose": True,
        },
        "credentials_ref": "dev:default",
        **overrides,
    }
    r = client.post(f"/projects/{project_id}/deployment-targets", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_patch_target_updates_fields(client_strict):
    h = _register(client_strict)
    pid = _project_id(client_strict, h)
    target = _create_target(client_strict, h, pid)

    pr = client_strict.patch(
        f"/deployment-targets/{target['id']}",
        headers=h,
        json={
            "name": "Updated Host",
            "config_json": {
                "host": "10.0.0.2",
                "ssh_user": "ubuntu",
                "remote_workdir": "/opt/cns-updated",
                "supports_compose": True,
            },
            "credentials_ref": "env:CNS_TEST_SSH_KEY_PATH",
            "status": "disabled",
        },
    )
    assert pr.status_code == 200, pr.text
    updated = pr.json()
    assert updated["name"] == "Updated Host"
    assert updated["target_type"] == "remote_docker"
    assert updated["status"] == "disabled"
    assert updated["config_json"]["host"] == "10.0.0.2"
    assert updated["credentials_ref"] == "env:CNS_TEST_SSH_KEY_PATH"


def test_patch_target_rejects_target_type_change(client_strict):
    h = _register(client_strict)
    pid = _project_id(client_strict, h)
    target = _create_target(client_strict, h, pid)

    pr = client_strict.patch(
        f"/deployment-targets/{target['id']}",
        headers=h,
        json={"name": "Still Docker", "target_type": "terraform"},
    )
    assert pr.status_code == 200, pr.text
    assert pr.json()["target_type"] == "remote_docker"


def test_viewer_cannot_patch_target(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    owner_h = _register(client_strict, "own")
    pid = _project_id(client_strict, owner_h)
    target = _create_target(client_strict, owner_h, pid)

    viewer_email = f"v{uuid.uuid4().hex[:8]}@example.com"
    vr = client_strict.post(
        "/auth/register",
        json={"email": viewer_email, "password": "password123", "display_name": "Viewer"},
    )
    viewer_h = {"Authorization": f"Bearer {vr.json()['access_token']}"}
    inv = client_strict.post(
        f"/projects/{pid}/invitations",
        headers=owner_h,
        json={"email": viewer_email, "role": "viewer"},
    )
    assert inv.status_code in (200, 201), inv.text
    token = inv.json()["accept_token"]
    client_strict.post(f"/invitations/{token}/accept", headers=viewer_h)

    pr = client_strict.patch(
        f"/deployment-targets/{target['id']}",
        headers=viewer_h,
        json={"name": "Hacked"},
    )
    assert pr.status_code == 403


def test_generated_compose_has_no_version_field():
    runtime = extract_node_runtime_config({"command": "nginx -g 'daemon off;'"})
    bundle = TopologyExportBundle(
        topology_id=uuid.uuid4(),
        topology_name="lab",
        description=None,
        runtime_target="docker",
        networking_mode="docker_bridge",
        nodes=(
            ExportNode(
                id=uuid.uuid4(),
                name="web",
                node_type="generic",
                image="nginx:alpine",
                ip_address=None,
                service_name="web-abc12345",
                runtime=runtime,
                health_check=None,
            ),
        ),
        links=(),
        networks=("lab-net",),
    )
    text = generate_docker_compose(bundle)
    assert '\nversion:' not in f"\n{text}"
    assert "services:" in text


def test_alpine_client_default_command_is_sleep_infinity():
    runtime = extract_node_runtime_config({})
    bundle = TopologyExportBundle(
        topology_id=uuid.uuid4(),
        topology_name="lab",
        description=None,
        runtime_target="docker",
        networking_mode="docker_bridge",
        nodes=(
            ExportNode(
                id=uuid.uuid4(),
                name="client",
                node_type="host",
                image="alpine:latest",
                ip_address=None,
                service_name="client-abc12345",
                runtime=runtime,
                health_check=None,
            ),
        ),
        links=(),
        networks=("lab-net",),
    )
    text = generate_docker_compose(bundle)
    assert 'command: ["sleep", "infinity"]' in text


def test_nginx_service_command_is_unchanged():
    runtime = extract_node_runtime_config({"command": "nginx -g 'daemon off;'"})
    bundle = TopologyExportBundle(
        topology_id=uuid.uuid4(),
        topology_name="lab",
        description=None,
        runtime_target="docker",
        networking_mode="docker_bridge",
        nodes=(
            ExportNode(
                id=uuid.uuid4(),
                name="web",
                node_type="generic",
                image="nginx:alpine",
                ip_address=None,
                service_name="web-abc12345",
                runtime=runtime,
                health_check=None,
            ),
        ),
        links=(),
        networks=("lab-net",),
    )
    text = generate_docker_compose(bundle)
    assert "sleep" not in text
    assert "nginx" in text
    assert "command:" in text
