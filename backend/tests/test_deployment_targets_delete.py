"""Tests for deployment target delete and infra linkage."""

from __future__ import annotations

import uuid

TOPOLOGY_BODY = {
    "name": "Target Delete Lab",
    "description": "target delete",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client, prefix: str = "td") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "TD"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _project_id(client, headers) -> str:
    return client.get("/projects", headers=headers).json()[0]["id"]


def _create_target(client, headers, project_id: str, **overrides) -> dict:
    body = {
        "name": "Delete Me Host",
        "target_type": "remote_docker",
        "config_json": {
            "host": "10.0.0.5",
            "ssh_user": "ubuntu",
            "ssh_port": 22,
            "remote_workdir": "/opt/cns-external-deployments",
            "supports_compose": True,
        },
        "credentials_ref": "env:CNS_TEST_SSH_KEY_PATH",
        **overrides,
    }
    r = client.post(f"/projects/{project_id}/deployment-targets", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_deployment_target_succeeds(client_strict):
    h = _register(client_strict)
    pid = _project_id(client_strict, h)
    target = _create_target(client_strict, h, pid)
    dr = client_strict.delete(f"/deployment-targets/{target['id']}", headers=h)
    assert dr.status_code == 204, dr.text
    gr = client_strict.get(f"/deployment-targets/{target['id']}", headers=h)
    assert gr.status_code == 404


def test_delete_target_with_active_external_deployment_rejected(client_strict, monkeypatch, tmp_path):
    key_file = tmp_path / "test.pem"
    key_file.write_text("fake-key\n")
    monkeypatch.setenv("CNS_TEST_SSH_KEY_PATH", str(key_file))

    from app.services.remote_command_runner import RemoteCommandResult, set_remote_command_runner

    class _Runner:
        def run_ssh(self, conn, remote_command, *, timeout_seconds=120):
            if "docker compose" in remote_command and " up -d" in remote_command:
                return RemoteCommandResult(0, "Container started", "")
            return RemoteCommandResult(0, "ok", "")

        def upload_files(self, conn, local_paths, remote_dir, *, timeout_seconds=120):
            return RemoteCommandResult(0, "", "")

    set_remote_command_runner(_Runner())
    try:
        h = _register(client_strict)
        pid = _project_id(client_strict, h)
        tr = client_strict.post("/topologies", headers=h, json={**TOPOLOGY_BODY, "project_id": pid})
        assert tr.status_code == 201, tr.text
        topo_id = tr.json()["id"]
        target = _create_target(client_strict, h, pid)
        apply = client_strict.post(
            f"/topologies/{topo_id}/external-deployment-jobs",
            headers=h,
            json={"target_id": target["id"], "mode": "apply"},
        )
        assert apply.status_code == 201, apply.text
        assert apply.json()["status"] == "succeeded", apply.text
        dep_list = client_strict.get(f"/topologies/{topo_id}/external-deployments", headers=h)
        assert dep_list.status_code == 200
        assert any(d["status"] == "active" for d in dep_list.json()["items"])
        dr = client_strict.delete(f"/deployment-targets/{target['id']}", headers=h)
        assert dr.status_code == 409, dr.text
        assert "active workload deployments" in dr.json()["detail"].lower()
    finally:
        set_remote_command_runner(None)
