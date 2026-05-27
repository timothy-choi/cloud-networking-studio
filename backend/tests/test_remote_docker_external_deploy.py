"""Tests for remote_docker external deployment executor (Step 57B)."""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field

import pytest

from app.services.remote_command_runner import (
    RemoteCommandResult,
    RemoteHostConnection,
    set_remote_command_runner,
)

TOPOLOGY_BODY = {
    "name": "Remote Docker Lab",
    "description": "step 57b",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}

REMOTE_DOCKER_CONFIG = {
    "host": "docker.example.com",
    "ssh_user": "ubuntu",
    "ssh_port": 22,
    "remote_workdir": "/opt/cns-external-deployments",
    "supports_compose": True,
}


@dataclass
class MockRemoteCommandRunner:
    ssh_commands: list[str] = field(default_factory=list)
    ssh_connections: list[RemoteHostConnection] = field(default_factory=list)
    uploads: list[tuple[str, list[tuple[str, str]], str]] = field(default_factory=list)

    def run_ssh(
        self,
        conn: RemoteHostConnection,
        remote_command: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        self.ssh_connections.append(conn)
        self.ssh_commands.append(remote_command)
        if "docker --version" in remote_command:
            return RemoteCommandResult(0, "Docker version 26.0.0", "")
        if "docker compose version" in remote_command:
            return RemoteCommandResult(0, "Docker Compose version v2.27.0", "")
        if "docker compose" in remote_command and " up -d" in remote_command:
            return RemoteCommandResult(0, "Container started", "")
        if "docker compose" in remote_command and " down" in remote_command:
            return RemoteCommandResult(0, "Container stopped", "")
        if remote_command.startswith("mkdir -p"):
            return RemoteCommandResult(0, "", "")
        return RemoteCommandResult(0, "ok", "")

    def upload_files(
        self,
        conn: RemoteHostConnection,
        local_paths: list[tuple[str, str]],
        remote_dir: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        self.uploads.append((conn.host, local_paths, remote_dir))
        return RemoteCommandResult(0, "uploaded", "")


@pytest.fixture
def ssh_key_env(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem") as fh:
        fh.write("-----BEGIN TEST KEY-----\n")
        key_path = fh.name
    monkeypatch.setenv("CNS_TEST_SSH_KEY_PATH", key_path)
    yield key_path


@pytest.fixture
def mock_runner():
    runner = MockRemoteCommandRunner()
    set_remote_command_runner(runner)
    yield runner
    set_remote_command_runner(None)


def _register(client, prefix: str = "rd") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "RD"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _project_and_topology(client, headers) -> tuple[str, str]:
    pid = client.get("/projects", headers=headers).json()[0]["id"]
    tr = client.post("/topologies", headers=headers, json={**TOPOLOGY_BODY, "project_id": pid})
    assert tr.status_code == 201, tr.text
    return pid, tr.json()["id"]


def _create_remote_target(client, headers, project_id: str, **overrides) -> dict:
    body = {
        "name": "Remote Docker Host",
        "target_type": "remote_docker",
        "config_json": REMOTE_DOCKER_CONFIG,
        "credentials_ref": "env:CNS_TEST_SSH_KEY_PATH",
        **overrides,
    }
    r = client.post(f"/projects/{project_id}/deployment-targets", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_validate_missing_config_fails_gracefully(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(
        client_strict,
        h,
        pid,
        config_json={"host": "10.0.0.1"},
    )

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "validate"},
    )
    assert jr.status_code == 201, jr.text
    job = jr.json()
    assert job["status"] == "failed"
    assert "Missing required remote_docker config fields" in (job["logs"] or "")
    assert mock_runner.ssh_commands == []


def test_validate_mocked_ssh_succeeds(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(client_strict, h, pid)

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "validate"},
    )
    assert jr.status_code == 201, jr.text
    job = jr.json()
    assert job["status"] == "succeeded"
    logs = job["logs"] or ""
    assert "[remote-docker]" in logs
    assert "Validation succeeded" in logs
    assert "ssh IdentitiesOnly=yes enabled" in logs
    assert "ssh key_path=" in logs
    assert "ssh key_readable=true" in logs
    assert any("docker --version" in c for c in mock_runner.ssh_commands)
    assert any("docker compose version" in c for c in mock_runner.ssh_commands)
    assert f"ssh key_path={ssh_key_env}" in logs
    assert "-----BEGIN TEST KEY-----" not in logs
    assert mock_runner.ssh_connections
    conn = mock_runner.ssh_connections[0]
    assert conn.known_hosts_file == f"/tmp/cns_known_hosts_{target['id']}"
    assert conn.key_path == ssh_key_env


def test_validate_gcp_generated_target_ssh_options(client_strict, monkeypatch, tmp_path, mock_runner):
    key_file = tmp_path / "gcp-remote-docker-key"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))

    h = _register(client_strict, prefix="gcpssh")
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(
        client_strict,
        h,
        pid,
        name="GCP Generated Target",
        credentials_ref="env:CNS_REMOTE_DOCKER_SSH_KEY_PATH",
        config_json={
            "host": "104.155.166.99",
            "ssh_user": "tchoi720",
            "ssh_port": 22,
            "remote_workdir": "/opt/cns-external-deployments",
            "supports_compose": True,
            "target_source": "terraform_gcp_docker_vm",
            "infrastructure_source": "terraform_gcp_docker_vm",
        },
    )

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "validate"},
    )
    assert jr.status_code == 201, jr.text
    job = jr.json()
    assert job["status"] == "succeeded"
    logs = job["logs"] or ""
    assert "ssh key_path=" + str(key_file) in logs
    assert "IdentitiesOnly=yes" in logs
    conn = mock_runner.ssh_connections[0]
    assert conn.key_path == str(key_file)
    assert conn.user == "tchoi720"
    assert conn.known_hosts_file == f"/tmp/cns_known_hosts_{target['id']}"


def test_plan_generates_compose_artifact(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(client_strict, h, pid)

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
    assert job["artifact_refs"][0].get("compose_project_name", "").startswith("cns-ext-")
    assert mock_runner.ssh_commands == []


def test_apply_mocked_ssh_scp_and_compose(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(client_strict, h, pid)

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "apply"},
    )
    assert jr.status_code == 201, jr.text
    job = jr.json()
    assert job["status"] == "succeeded"
    assert mock_runner.uploads
    uploaded_names = {name for _, pairs, _ in mock_runner.uploads for _, name in pairs}
    assert "docker-compose.cns.yml" in uploaded_names
    assert "metadata.json" in uploaded_names
    assert any(" up -d" in cmd for cmd in mock_runner.ssh_commands)

    dep_list = client_strict.get(f"/topologies/{tid}/external-deployments", headers=h)
    assert dep_list.status_code == 200
    items = dep_list.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "active"
    assert items[0]["compose_project_name"].startswith("cns-ext-")


def test_destroy_mocked_ssh_compose_down(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(client_strict, h, pid)

    apply_r = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "apply"},
    )
    assert apply_r.status_code == 201
    assert apply_r.json()["status"] == "succeeded"

    destroy_r = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "destroy"},
    )
    assert destroy_r.status_code == 201, destroy_r.text
    job = destroy_r.json()
    assert job["status"] == "succeeded"
    assert any(" down" in cmd for cmd in mock_runner.ssh_commands)

    dep_list = client_strict.get(f"/topologies/{tid}/external-deployments", headers=h)
    active = [d for d in dep_list.json()["items"] if d["status"] == "active"]
    destroyed = [d for d in dep_list.json()["items"] if d["status"] == "destroyed"]
    assert active == []
    assert len(destroyed) == 1


def test_apply_mode_enabled_for_remote_docker(client_strict, ssh_key_env, mock_runner):
    h = _register(client_strict)
    pid, tid = _project_and_topology(client_strict, h)
    target = _create_remote_target(client_strict, h, pid)

    jr = client_strict.post(
        f"/topologies/{tid}/external-deployment-jobs",
        headers=h,
        json={"target_id": target["id"], "mode": "apply"},
    )
    assert jr.status_code == 201
    assert jr.json()["status"] == "succeeded"


def test_legacy_infra_target_types_rejected_at_create(client_strict):
    h = _register(client_strict)
    pid, _ = _project_and_topology(client_strict, h)
    tr = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=h,
        json={
            "name": "TF",
            "target_type": "terraform",
            "config_json": {"backend": "local"},
        },
    )
    assert tr.status_code == 400, tr.text
    detail = tr.json()["detail"]
    assert "runtime target" in detail.lower()
    assert "Infrastructure Deployments" in detail
