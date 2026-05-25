"""Tests for remote_docker SSH runtime, credentials, and compose wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.remote_command_runner import (
    RemoteCommandResult,
    RemoteHostConnection,
    SubprocessRemoteCommandRunner,
    set_remote_command_runner,
)
from app.services.remote_credentials_service import resolve_ssh_key_path
from app.services.remote_ssh_runtime import (
    SSH_CLIENT_MISSING_MESSAGE,
    ensure_ssh_client_installed,
    raise_for_ssh_failure,
    ssh_client_status,
)


def test_env_credentials_ref_resolves_when_env_var_set(tmp_path, monkeypatch):
    key_file = tmp_path / "id.pem"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))
    assert resolve_ssh_key_path("env:CNS_REMOTE_DOCKER_SSH_KEY_PATH") == str(key_file)


def test_empty_env_var_fails_clearly(monkeypatch):
    monkeypatch.delenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", raising=False)
    with pytest.raises(ValueError, match="env:CNS_REMOTE_DOCKER_SSH_KEY_PATH is not set on the server"):
        resolve_ssh_key_path("env:CNS_REMOTE_DOCKER_SSH_KEY_PATH")


def test_unreadable_key_path_fails_clearly(tmp_path, monkeypatch):
    key_file = tmp_path / "missing.pem"
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))
    with pytest.raises(ValueError, match="not readable by backend container"):
        resolve_ssh_key_path("env:CNS_REMOTE_DOCKER_SSH_KEY_PATH")


def test_non_readable_key_file_fails_clearly(tmp_path, monkeypatch):
    key_file = tmp_path / "locked.pem"
    key_file.write_text("fake-key\n", encoding="utf-8")
    key_file.chmod(0o000)
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))
    try:
        with pytest.raises(ValueError, match="not readable by backend container"):
            resolve_ssh_key_path("env:CNS_REMOTE_DOCKER_SSH_KEY_PATH")
    finally:
        key_file.chmod(0o644)


def test_missing_ssh_binary_fails_clearly(monkeypatch):
    monkeypatch.setattr("app.services.remote_ssh_runtime.shutil.which", lambda name: None)
    ok, _message = ssh_client_status()
    assert ok is False
    with pytest.raises(ValueError, match=SSH_CLIENT_MISSING_MESSAGE):
        ensure_ssh_client_installed()


def test_raise_for_ssh_permission_denied():
    result = RemoteCommandResult(255, "", "ubuntu@host: Permission denied (publickey).")
    with pytest.raises(ValueError, match="SSH permission denied"):
        raise_for_ssh_failure(result, context="SSH")


def test_subprocess_runner_invokes_ssh_and_scp(tmp_path, monkeypatch):
    key_file = tmp_path / "key.pem"
    key_file.write_text("k\n", encoding="utf-8")
    conn = RemoteHostConnection(host="1.2.3.4", user="ubuntu", port=22, key_path=str(key_file))
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr("app.services.remote_command_runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "app.services.remote_command_runner.ensure_ssh_client_installed",
        lambda: None,
    )
    runner = SubprocessRemoteCommandRunner()
    runner.run_ssh(conn, "docker --version")
    local = tmp_path / "compose.yml"
    local.write_text("services: {}\n", encoding="utf-8")
    runner.upload_files(conn, [(str(local), "docker-compose.cns.yml")], "/opt/cns")
    assert any(cmd[0] == "ssh" for cmd in calls)
    assert any(cmd[0] == "scp" for cmd in calls)


def test_compose_backend_contains_env_and_secrets_mount():
    compose_text = Path(__file__).resolve().parents[2].joinpath("docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    assert "CNS_REMOTE_DOCKER_SSH_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-}" in compose_text
    assert "/opt/cns/secrets:/opt/cns/secrets:ro" in compose_text


def test_staging_compose_backend_remote_docker_ssh_key_default():
    compose_text = Path(__file__).resolve().parents[2].joinpath("docker-compose.staging.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "CNS_REMOTE_DOCKER_SSH_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-/opt/cns/secrets/gcp-remote-docker-key}"
        in compose_text
    )


def test_remote_docker_executor_uses_runner_for_validate(client_strict, monkeypatch, tmp_path):
    key_file = tmp_path / "test.pem"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_TEST_SSH_KEY_PATH", str(key_file))
    monkeypatch.setattr(
        "app.services.remote_docker_executor_service.ensure_ssh_client_installed",
        lambda: None,
    )

    commands: list[str] = []

    class _Runner:
        def run_ssh(self, conn, remote_command, *, timeout_seconds=120):
            commands.append(remote_command)
            if "docker compose version" in remote_command:
                return RemoteCommandResult(0, "Docker Compose version v2.27.0", "")
            return RemoteCommandResult(0, "Docker version 26.0.0", "")

        def upload_files(self, conn, local_paths, remote_dir, *, timeout_seconds=120):
            return RemoteCommandResult(0, "", "")

    set_remote_command_runner(_Runner())
    try:
        from tests.test_remote_docker_external_deploy import (
            _create_remote_target,
            _project_and_topology,
            _register,
        )

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
        assert job["status"] == "succeeded", job.get("logs")
        assert any("docker --version" in cmd for cmd in commands)
        assert any("docker compose version" in cmd for cmd in commands)
    finally:
        set_remote_command_runner(None)
