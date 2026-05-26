"""Tests for GCP docker-vm SSH public key provisioning (Step 57E)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GCP_DOCKER_VM_MAIN = REPO_ROOT / "infra_templates/terraform/gcp/docker_vm/main.tf"
GCP_DOCKER_VM_VARS = REPO_ROOT / "infra_templates/terraform/gcp/docker_vm/variables.tf"

SSH_PUB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtestkey cns-remote-docker"


def _write_ssh_keys(tmp_path, monkeypatch) -> tuple[Path, Path]:
    priv = tmp_path / "gcp-remote-docker-key"
    pub = tmp_path / "gcp-remote-docker-key.pub"
    priv.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n")
    pub.write_text(f"{SSH_PUB}\n")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_KEY_PATH", str(priv))
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(pub))
    return priv, pub


def test_gcp_docker_vm_template_disables_os_login_and_injects_ssh_keys():
    main_tf = GCP_DOCKER_VM_MAIN.read_text(encoding="utf-8")
    variables_tf = GCP_DOCKER_VM_VARS.read_text(encoding="utf-8")

    assert 'enable-oslogin = "FALSE"' in main_tf
    assert "ssh-keys" in main_tf
    assert "var.ssh_public_key" in main_tf
    assert "var.ssh_user" in main_tf
    assert 'variable "ssh_public_key"' in variables_tf


def test_resolve_remote_docker_ssh_public_key_reads_file(tmp_path, monkeypatch):
    from app.services.remote_ssh_public_key_service import resolve_remote_docker_ssh_public_key

    _, pub = _write_ssh_keys(tmp_path, monkeypatch)
    assert resolve_remote_docker_ssh_public_key() == SSH_PUB


def test_resolve_remote_docker_ssh_public_key_missing_file(tmp_path, monkeypatch):
    from app.services.remote_ssh_public_key_service import resolve_remote_docker_ssh_public_key

    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(tmp_path / "missing.pub"))
    with pytest.raises(ValueError, match="CNS remote Docker SSH public key is not configured"):
        resolve_remote_docker_ssh_public_key()


def test_gcp_apply_payload_includes_ssh_public_key(monkeypatch, tmp_path):
    import uuid
    from types import SimpleNamespace

    from app.services.terraform_executor_service import _base_payload

    _write_ssh_keys(tmp_path, monkeypatch)
    cred_file = tmp_path / "gcp-sa.json"
    cred_file.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))

    dep_id = uuid.uuid4()
    deployment = SimpleNamespace(
        id=dep_id,
        topology_id=uuid.uuid4(),
        name="gcp-stack",
        template_id="docker-vm",
        provider="gcp",
        status="awaiting_confirmation",
        variables_json={
            "project_id": "my-gcp-project",
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "e2-medium",
            "instance_name": "cns-docker-vm",
            "ssh_user": "ubuntu",
            "vm_count": 1,
        },
        credentials_ref="env:GOOGLE_APPLICATION_CREDENTIALS",
    )
    execution = SimpleNamespace(id=uuid.uuid4())

    payload = _base_payload(execution=execution, deployment=deployment, mode="apply")
    assert payload["variables"]["ssh_public_key"] == SSH_PUB
    assert payload["variables"]["ssh_user"] == "ubuntu"


def _clear_ssh_public_key(monkeypatch, tmp_path) -> None:
    """Force missing public key — delenv alone still falls back to the default path on CI."""
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(tmp_path / "missing-cns-remote-docker-key.pub"))


def test_gcp_plan_fails_without_ssh_public_key(client_strict, monkeypatch, tmp_path):
    import json
    import uuid

    from tests.test_infrastructure_deployments_57d import _install_runner

    cred_file = tmp_path / "gcp-sa.json"
    cred_file.write_text(json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))
    _clear_ssh_public_key(monkeypatch, tmp_path)
    _install_runner(monkeypatch)

    email = f"nopub{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "NoPub"},
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=h,
        json={
            "name": "NoPub",
            "description": "x",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]

    from tests.test_infrastructure_deployments_57e import GCP_VARS

    dep_id = client_strict.post(
        f"/topologies/{topo}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-no-pub",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    ).json()["id"]

    validate = client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    assert validate.status_code == 200, validate.text
    body = validate.json()
    assert body["status"] == "failed"
    assert "SSH public key is not configured" in (body.get("error_message") or "")


def test_gcp_apply_blocked_without_ssh_public_key(client_strict, monkeypatch, tmp_path):
    import json
    import uuid

    from tests.test_infrastructure_deployments_57d import _install_runner
    from tests.test_infrastructure_deployments_57e import GCP_VARS, _gcp_credentials

    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    _clear_ssh_public_key(monkeypatch, tmp_path)

    email = f"applynopub{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "ApplyNoPub"},
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=h,
        json={
            "name": "ApplyNoPub",
            "description": "x",
            "project_id": pid,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    dep_id = client_strict.post(
        f"/topologies/{topo}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-apply-no-pub",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    ).json()["id"]

    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    plan = client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["status"] == "failed"
    assert "SSH public key is not configured" in (body.get("error_message") or "")
