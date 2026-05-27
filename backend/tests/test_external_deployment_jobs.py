"""Tests for external deployment targets and jobs (Step 57A)."""

from __future__ import annotations

import uuid

TOPOLOGY_BODY = {
    "name": "External Deploy Lab",
    "description": "step 57a",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client, prefix: str = "ext") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Ext"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _project_and_topology(client, headers) -> tuple[str, str]:
    pid = client.get("/projects", headers=headers).json()[0]["id"]
    tr = client.post("/topologies", headers=headers, json={**TOPOLOGY_BODY, "project_id": pid})
    assert tr.status_code == 201, tr.text
    return pid, tr.json()["id"]


def _create_target(client, headers, project_id: str, **overrides) -> dict:
    body = {
        "name": "Staging Docker Host",
        "target_type": "remote_docker",
        "config_json": {
            "host": "docker.example.com",
            "ssh_user": "ubuntu",
            "ssh_port": 22,
            "remote_workdir": "/opt/cns-external-deployments",
            "supports_compose": True,
        },
        "credentials_ref": "dev:default",
        **overrides,
    }
    r = client.post(f"/projects/{project_id}/deployment-targets", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list_deployment_targets(client_strict):
    h = _register(client_strict)
    pid, _ = _project_and_topology(client_strict, h)

    target = _create_target(client_strict, h, pid)
    assert target["target_type"] == "remote_docker"
    assert target["credentials_ref"] == "dev:default"
    assert target["status"] == "active"

    lst = client_strict.get(f"/projects/{pid}/deployment-targets", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()["items"]) == 1

    detail = client_strict.get(f"/deployment-targets/{target['id']}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["name"] == "Staging Docker Host"


def test_create_validate_job_and_logs(client_strict, monkeypatch, tmp_path):
    key_file = tmp_path / "test.pem"
    key_file.write_text("fake-key\n")
    monkeypatch.setenv("CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH", str(key_file))

    from app.services.remote_command_runner import RemoteCommandResult, set_remote_command_runner

    class _Runner:
        def run_ssh(self, conn, remote_command, *, timeout_seconds=120):
            return RemoteCommandResult(0, "Docker version 26.0.0", "")

        def upload_files(self, conn, local_paths, remote_dir, *, timeout_seconds=120):
            return RemoteCommandResult(0, "", "")

    set_remote_command_runner(_Runner())
    try:
        h = _register(client_strict)
        pid, tid = _project_and_topology(client_strict, h)
        target = _create_target(client_strict, h, pid)

        jr = client_strict.post(
            f"/topologies/{tid}/external-deployment-jobs",
            headers=h,
            json={"target_id": target["id"], "mode": "validate"},
        )
        assert jr.status_code == 201, jr.text
        job = jr.json()
        assert job["mode"] == "validate"
        assert job["status"] == "succeeded"
        assert job["logs"]
        assert "[remote-docker]" in job["logs"].lower()
        assert "validation succeeded" in job["logs"].lower()
        assert f"ssh key_path={key_file}" in job["logs"]
        assert "IdentitiesOnly=yes" in job["logs"]
        assert "fake-key" not in job["logs"]

        gr = client_strict.get(f"/external-deployment-jobs/{job['id']}", headers=h)
        assert gr.status_code == 200
        assert gr.json()["status"] == "succeeded"

        lr = client_strict.get(f"/external-deployment-jobs/{job['id']}/logs", headers=h)
        assert lr.status_code == 200
        assert lr.json()["logs"] == job["logs"]

        lst = client_strict.get(f"/topologies/{tid}/external-deployment-jobs", headers=h)
        assert lst.status_code == 200
        assert any(j["id"] == job["id"] for j in lst.json()["items"])
    finally:
        set_remote_command_runner(None)


def test_plan_job_returns_artifact_refs(client_strict):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_target(
        client_strict,
        h,
        pid,
        target_type="kubernetes",
        config_json={"namespace": "cns-lab", "context": "staging"},
    )

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "plan"},
    )
    assert jr.status_code == 201, jr.text
    job = jr.json()
    assert job["status"] == "succeeded"
    assert job["artifact_refs"]
    assert job["artifact_refs"][0]["type"] == "plan_summary"
    assert job["artifact_refs"][0]["target_type"] == "kubernetes"


def test_apply_mode_rejected_for_non_remote_docker(client_strict):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_target(
        client_strict,
        h,
        pid,
        target_type="kubernetes",
        config_json={"namespace": "cns-lab", "context": "staging"},
    )

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "apply"},
    )
    assert jr.status_code == 400
    assert "not enabled" in jr.json()["detail"].lower()


def test_legacy_infra_target_types_rejected_at_create(client_strict):
    h = _register(client_strict)
    pid, _ = _project_and_topology(client_strict, h)

    for target_type, config_json in (
        ("terraform", {"backend": "local"}),
        ("ansible", {"host": "10.0.0.1"}),
    ):
        r = client_strict.post(
            f"/projects/{pid}/deployment-targets",
            headers=h,
            json={"name": f"Legacy {target_type}", "target_type": target_type, "config_json": config_json},
        )
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert "runtime target" in detail.lower()
        assert "Infrastructure Deployments" in detail


def test_viewer_cannot_create_target_or_job(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    owner_h = _register(client_strict, "own")
    pid, tid = _project_and_topology(client_strict, owner_h)

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

    tr = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=viewer_h,
        json={"name": "x", "target_type": "remote_docker", "config_json": {}},
    )
    assert tr.status_code == 403

    target = _create_target(client_strict, owner_h, pid)
    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=viewer_h,
        json={"target_id": target["id"], "mode": "validate"},
    )
    assert jr.status_code == 403


def test_secrets_scrubbed_from_target_config(client_strict):
    h = _register(client_strict)
    pid, _ = _project_and_topology(client_strict, h)

    r = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=h,
        json={
            "name": "Secret host",
            "target_type": "remote_docker",
            "config_json": {
                "password": "super-secret",
                "host": "10.0.0.1",
                "ssh_user": "ubuntu",
                "remote_workdir": "/opt/cns-external-deployments",
            },
            "credentials_ref": "env:CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH",
        },
    )
    assert r.status_code == 201, r.text
    cfg = r.json()["config_json"]
    assert cfg.get("password") == "[redacted]" or "redacted" in str(cfg.get("password", ""))
