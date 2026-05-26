"""Tests for GCP post-apply SSH readiness and Ansible host key handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import uuid
from types import SimpleNamespace

import pytest

from app.services import ansible_executor_service as ansible_svc
from app.services import infra_ssh_readiness as ssh_readiness
from app.services.remote_command_runner import RemoteCommandResult, RemoteHostConnection


def _gcp_deployment(**overrides):
    defaults = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "project_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "topology_id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
        "name": "gcp-stack",
        "template_id": "docker-vm",
        "provider": "gcp",
        "status": "configuring",
        "variables_json": {"ssh_user": "ubuntu"},
        "outputs_json": {
            "public_ip": "203.0.113.55",
            "private_ip": "10.128.0.5",
            "instance_name": "cns-docker-vm",
            "ssh_user": "ubuntu",
            "hosts": [],
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_known_hosts_path_is_per_deployment():
    dep_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert ssh_readiness.known_hosts_path(dep_id) == f"/tmp/cns-known-hosts-{dep_id}"


def test_inventory_includes_ephemeral_vm_ssh_vars(tmp_path, monkeypatch):
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))

    dep = _gcp_deployment()
    inventory = ansible_svc.generate_inventory(dep)
    host = inventory["all"]["children"]["cns_runtime"]["hosts"][0]
    ini = ansible_svc.inventory_ini_preview(inventory)

    assert host["ansible_host_key_checking"] is False
    assert "StrictHostKeyChecking=no" in host["ansible_ssh_common_args"]
    assert f"/tmp/cns-known-hosts-{dep.id}" in host["ansible_ssh_common_args"]
    assert host["ansible_ssh_private_key_file"] == str(key_file)
    assert "ansible_host_key_checking=False" in ini
    assert "StrictHostKeyChecking=no" in ini


def test_wait_for_ssh_ready_retries_tcp_refused(monkeypatch):
    dep = _gcp_deployment()
    tcp_calls: list[tuple[str, int]] = []

    def fake_tcp(host, port, *, timeout_seconds=5.0):
        tcp_calls.append((host, port))
        return len(tcp_calls) >= 3

    ssh_calls = {"count": 0}

    def fake_probe(conn, *, timeout_seconds=15):
        ssh_calls["count"] += 1
        return True, "cns-ssh-ready"

    monkeypatch.setattr(ssh_readiness, "check_tcp_port", fake_tcp)
    monkeypatch.setattr(ssh_readiness, "probe_ssh_auth", fake_probe)
    monkeypatch.setattr(ssh_readiness, "resolve_ssh_key_path", lambda _ref: "/tmp/fake-key")
    monkeypatch.setattr(ssh_readiness.time, "sleep", lambda _seconds: None)

    log = ssh_readiness.wait_for_ssh_ready(
        dep,
        timeout_seconds=60,
        interval_seconds=1,
    )

    assert len(tcp_calls) >= 3
    assert ssh_calls["count"] == 1
    assert "all hosts ready" in log


def test_wait_for_ssh_ready_times_out(monkeypatch):
    dep = _gcp_deployment()
    ticks = {"value": 0.0}

    def fake_monotonic() -> float:
        ticks["value"] += 10.0
        return ticks["value"]

    monkeypatch.setattr(ssh_readiness.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(ssh_readiness, "check_tcp_port", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(ssh_readiness.time, "sleep", lambda _seconds: None)

    with pytest.raises(ValueError, match="SSH readiness timed out"):
        ssh_readiness.wait_for_ssh_ready(dep, timeout_seconds=15, interval_seconds=1)


def test_verify_remote_docker_requires_compose(monkeypatch):
    dep = _gcp_deployment()
    runner = MagicMock()
    runner.run_ssh.side_effect = [
        RemoteCommandResult(0, "Docker version 24.0.0", ""),
        RemoteCommandResult(127, "", "docker: 'compose' is not a docker command"),
    ]
    monkeypatch.setattr(ssh_readiness, "get_remote_command_runner", lambda: runner)
    monkeypatch.setattr(ssh_readiness, "resolve_ssh_key_path", lambda _ref: "/tmp/fake-key")

    with pytest.raises(ValueError, match="docker compose version"):
        ssh_readiness.verify_remote_docker(dep)


def test_remote_connection_uses_per_deployment_known_hosts(tmp_path, monkeypatch):
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(key_file))

    dep = _gcp_deployment()
    host = ssh_readiness.resolve_inventory_hosts(dep)[0]
    conn = ssh_readiness._remote_connection(dep, host)

    assert conn.known_hosts_file == f"/tmp/cns-known-hosts-{dep.id}"
    assert conn.key_path == str(key_file)

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return type("P", (), {"returncode": 0, "stdout": "cns-ssh-ready", "stderr": ""})()

    monkeypatch.setattr("app.services.remote_command_runner.subprocess.run", fake_run)
    monkeypatch.setattr("app.services.remote_command_runner.ensure_ssh_client_installed", lambda: None)

    from app.services.remote_command_runner import SubprocessRemoteCommandRunner

    SubprocessRemoteCommandRunner().run_ssh(conn, "echo cns-ssh-ready")
    ssh_cmd = captured[0]
    assert "StrictHostKeyChecking=no" in ssh_cmd
    assert f"UserKnownHostsFile=/tmp/cns-known-hosts-{dep.id}" in ssh_cmd
