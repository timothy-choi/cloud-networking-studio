"""Tests for external deployment SSH options (GCP generated runtime targets)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.remote_command_runner import RemoteHostConnection, build_ssh_argv, format_ssh_command_for_log
from app.services.remote_docker_executor_service import (
    REMOTE_DOCKER_SSH_CREDENTIALS_REF,
    _connection,
    external_ssh_known_hosts_path,
    parse_remote_docker_config,
)


def test_external_ssh_known_hosts_path_uses_target_id():
    target_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert external_ssh_known_hosts_path(target_id) == f"/tmp/cns_known_hosts_{target_id}"


def test_build_ssh_argv_includes_identities_only_and_known_hosts(tmp_path):
    key_file = tmp_path / "gcp-remote-docker-key"
    key_file.write_text("fake-key\n", encoding="utf-8")
    conn = RemoteHostConnection(
        host="104.155.166.99",
        user="tchoi720",
        port=22,
        key_path=str(key_file),
        known_hosts_file="/tmp/cns_known_hosts_manual",
    )
    argv = build_ssh_argv(conn, "docker --version")
    assert argv[0] == "ssh"
    assert "-i" in argv and str(key_file) in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=no" in argv
    assert "UserKnownHostsFile=/tmp/cns_known_hosts_manual" in argv
    assert argv[-1] == "docker --version"
    assert "tchoi720@104.155.166.99" in argv


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
