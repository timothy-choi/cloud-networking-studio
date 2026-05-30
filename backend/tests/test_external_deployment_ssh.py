"""Tests for external deployment SSH/SCP options (GCP generated runtime targets)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.remote_command_runner import (
    RemoteHostConnection,
    SubprocessRemoteCommandRunner,
    build_scp_upload_argv,
    build_ssh_argv,
    build_ssh_shared_options,
    format_scp_command_for_log,
    format_ssh_command_for_log,
    ssh_options_summary,
)
from app.services.remote_docker_executor_service import (
    REMOTE_DOCKER_SSH_CREDENTIALS_REF,
    _connection,
    external_ssh_known_hosts_path,
    parse_remote_docker_config,
)
from app.services.remote_ssh_runtime import (
    SCP_WRITE_PERMISSION_DENIED_MESSAGE,
    SSH_PERMISSION_DENIED_MESSAGE,
    raise_for_ssh_failure,
)
from app.services.remote_command_runner import RemoteCommandResult


def _sample_conn(tmp_path, *, known_hosts: str = "/tmp/cns_known_hosts_manual") -> RemoteHostConnection:
    key_file = tmp_path / "gcp-remote-docker-key"
    key_file.write_text("fake-key\n", encoding="utf-8")
    return RemoteHostConnection(
        host="104.155.166.99",
        user="tchoi720",
        port=22,
        key_path=str(key_file),
        known_hosts_file=known_hosts,
    )


def test_external_ssh_known_hosts_path_uses_target_id():
    target_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert external_ssh_known_hosts_path(target_id) == f"/tmp/cns_known_hosts_{target_id}"


def test_build_ssh_shared_options_includes_identities_only_and_known_hosts(tmp_path):
    conn = _sample_conn(tmp_path)
    opts = build_ssh_shared_options(conn, include_connect_timeout=True)
    assert "-i" in opts and conn.key_path in opts
    assert "IdentitiesOnly=yes" in opts
    assert "StrictHostKeyChecking=no" in opts
    assert f"UserKnownHostsFile={conn.known_hosts_file}" in opts
    assert "ConnectTimeout=15" in opts


def test_build_ssh_argv_includes_identities_only_and_known_hosts(tmp_path):
    conn = _sample_conn(tmp_path)
    argv = build_ssh_argv(conn, "docker --version")
    assert argv[0] == "ssh"
    assert "-i" in argv and conn.key_path in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=no" in argv
    assert f"UserKnownHostsFile={conn.known_hosts_file}" in argv
    assert argv[-1] == "docker --version"
    assert "tchoi720@104.155.166.99" in argv


def test_build_scp_upload_argv_uses_shared_ssh_options(tmp_path):
    conn = _sample_conn(tmp_path)
    argv = build_scp_upload_argv(
        conn,
        "/tmp/compose.yml",
        "docker-compose.cns.yml",
        "/opt/cns-external-deployments/cns-abc/123",
    )
    assert argv[0] == "scp"
    assert "-i" in argv and conn.key_path in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=no" in argv
    assert f"UserKnownHostsFile={conn.known_hosts_file}" in argv
    assert argv[-1] == "tchoi720@104.155.166.99:/opt/cns-external-deployments/cns-abc/123/docker-compose.cns.yml"


def test_ssh_options_summary_and_log_formatters(tmp_path):
    conn = _sample_conn(tmp_path)
    summary = ssh_options_summary(conn)
    assert conn.key_path in summary
    assert "IdentitiesOnly=yes" in summary
    assert conn.known_hosts_file in summary

    ssh_preview = format_ssh_command_for_log(conn, "whoami")
    assert "IdentitiesOnly=yes" in ssh_preview
    assert conn.key_path in ssh_preview

    scp_preview = format_scp_command_for_log(conn, "/tmp/x.yml", "x.yml", "/opt/cns")
    assert "IdentitiesOnly=yes" in scp_preview
    assert conn.key_path in scp_preview
    assert "scp" in scp_preview


def test_validate_apply_destroy_subprocess_paths_use_shared_options(tmp_path, monkeypatch):
    conn = _sample_conn(tmp_path)
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
    runner.upload_files(conn, [(str(local), "docker-compose.cns.yml")], "/opt/cns-external-deployments/job")
    runner.run_ssh(conn, "docker compose down")

    ssh_cmds = [cmd for cmd in calls if cmd[0] == "ssh"]
    scp_cmds = [cmd for cmd in calls if cmd[0] == "scp"]
    assert len(ssh_cmds) == 3  # validate-style ssh + mkdir + destroy ssh
    assert len(scp_cmds) == 1
    for cmd in ssh_cmds + scp_cmds:
        assert "IdentitiesOnly=yes" in cmd
        assert conn.key_path in cmd
        assert f"UserKnownHostsFile={conn.known_hosts_file}" in cmd


def test_gcp_generated_target_connection_resolves_cns_ssh_key_env(tmp_path, monkeypatch):
    key_file = tmp_path / "gcp-remote-docker-key"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))

    target_id = uuid.uuid4()
    target = SimpleNamespace(
        id=target_id,
        credentials_ref=REMOTE_DOCKER_SSH_CREDENTIALS_REF,
    )
    cfg = parse_remote_docker_config(
        {
            "host": "104.155.166.99",
            "ssh_user": "tchoi720",
            "ssh_port": 22,
            "remote_workdir": "/opt/cns-external-deployments",
            "supports_compose": True,
            "target_source": "terraform_gcp_docker_vm",
            "infrastructure_source": "terraform_gcp_docker_vm",
        }
    )
    conn = _connection(target, cfg)
    assert conn.key_path == str(key_file)
    assert conn.known_hosts_file == f"/tmp/cns_known_hosts_{target_id}"
    preview = format_ssh_command_for_log(conn, "whoami && docker --version && docker compose version")
    assert "IdentitiesOnly=yes" in preview
    assert str(key_file) in preview
    assert "StrictHostKeyChecking=no" in preview
    assert f"UserKnownHostsFile=/tmp/cns_known_hosts_{target_id}" in preview
    assert "tchoi720@104.155.166.99" in preview


def test_raise_for_ssh_failure_distinguishes_scp_write_permission_denied():
    result = RemoteCommandResult(1, "", "scp: /opt/cns/file: Permission denied")
    with pytest.raises(ValueError, match=SCP_WRITE_PERMISSION_DENIED_MESSAGE):
        raise_for_ssh_failure(result, context="SCP upload")


def test_raise_for_ssh_failure_distinguishes_mkdir_permission_denied():
    result = RemoteCommandResult(1, "", "mkdir: cannot create directory: Permission denied")
    with pytest.raises(ValueError, match="Remote directory creation failed"):
        raise_for_ssh_failure(result, context="SSH mkdir")


def test_raise_for_ssh_failure_publickey_still_maps_to_ssh_auth_error():
    result = RemoteCommandResult(255, "", "Permission denied (publickey).")
    with pytest.raises(ValueError, match=SSH_PERMISSION_DENIED_MESSAGE):
        raise_for_ssh_failure(result, context="SCP upload")
