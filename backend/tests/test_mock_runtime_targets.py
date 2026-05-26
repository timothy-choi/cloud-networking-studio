"""Tests for mock runtime target external deployment jobs."""

from __future__ import annotations

import uuid

TOPOLOGY_BODY = {
    "name": "Mock Target Lab",
    "description": "mock validate",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _register(client, prefix: str = "mock") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Mock"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _project_and_topology(client, headers) -> tuple[str, str]:
    pid = client.get("/projects", headers=headers).json()[0]["id"]
    tr = client.post("/topologies", headers=headers, json={**TOPOLOGY_BODY, "project_id": pid})
    assert tr.status_code == 201, tr.text
    return pid, tr.json()["id"]


def test_mock_target_validate_is_simulated_without_ssh(client_strict, monkeypatch):
    ssh_attempted: list[str] = []

    from app.services.remote_command_runner import RemoteCommandResult, set_remote_command_runner

    class _Runner:
        def run_ssh(self, conn, remote_command, *, timeout_seconds=120):
            ssh_attempted.append(remote_command)
            return RemoteCommandResult(0, "ok", "")

        def upload_files(self, conn, local_paths, remote_dir, *, timeout_seconds=120):
            ssh_attempted.append("upload")
            return RemoteCommandResult(0, "", "")

    set_remote_command_runner(_Runner())
    try:
        h = _register(client_strict)
        pid, topo_id = _project_and_topology(client_strict, h)
        created = client_strict.post(
            f"/projects/{pid}/deployment-targets",
            headers=h,
            json={
                "name": "mock-runtime",
                "target_type": "remote_docker",
                "config_json": {
                    "host": "203.0.113.10",
                    "is_mock": True,
                    "target_source": "local_mock_infra",
                    "mock_label": "Mock target — workflow testing only",
                    "workload_apply_disabled": True,
                },
                "credentials_ref": "dev:default",
            },
        )
        assert created.status_code == 201, created.text
        target_id = created.json()["id"]

        jr = client_strict.post(
            f"/topologies/{topo_id}/external-deployment-jobs",
            headers=h,
            json={"target_id": target_id, "mode": "validate"},
        )
        assert jr.status_code == 201, jr.text
        job = jr.json()
        assert job["status"] == "succeeded"
        assert "[mock]" in (job.get("logs") or "").lower()
        assert "simulated validate" in (job.get("logs") or "").lower()
        assert ssh_attempted == []
    finally:
        set_remote_command_runner(None)


def test_mock_target_apply_rejected(client_strict):
    h = _register(client_strict)
    pid, topo_id = _project_and_topology(client_strict, h)
    created = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=h,
        json={
            "name": "mock-runtime",
            "target_type": "remote_docker",
            "config_json": {
                "host": "203.0.113.10",
                "is_mock": True,
                "target_source": "local_mock_infra",
                "workload_apply_disabled": True,
            },
        },
    )
    target_id = created.json()["id"]
    jr = client_strict.post(
        f"/topologies/{topo_id}/external-deployment-jobs",
        headers=h,
        json={"target_id": target_id, "mode": "apply"},
    )
    assert jr.status_code == 400, jr.text
    assert "disabled" in jr.json()["detail"].lower()
