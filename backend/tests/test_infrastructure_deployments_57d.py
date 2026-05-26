
"""Additional tests for Step 57D Terraform plan-only cloud providers."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

TOPOLOGY_BODY = {
    "name": "GCP Infra Lab",
    "description": "step 57d",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}

GCP_VARS = {
    "project_id": "my-gcp-project",
    "region": "us-central1",
    "zone": "us-central1-a",
    "machine_type": "e2-medium",
    "network_name": "default",
    "instance_name": "cns-docker-vm",
    "ssh_user": "ubuntu",
    "allowed_ssh_cidr": "203.0.113.0/24",
    "allowed_app_cidr": "203.0.113.0/24",
    "tags": "cns-docker-vm",
    "vm_count": 1,
}


@dataclass
class _CapturingInfraRunner:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_execution(self, payload: dict[str, Any]):
        from app.runtime.infra_runner_client import InfraExecutionResult

        self.calls.append(payload)
        mode = payload.get("mode")
        outputs = {
            "vm_count": 1,
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "e2-medium",
            "exposed_ports": [22, 80, 443],
            "firewall_rules": ["cns-docker-vm-allow-ssh", "cns-docker-vm-allow-app"],
            "estimated_resources": {"compute_instances": 1, "firewall_rules": 2},
            "warnings": ["Plan-only"],
            "hosts": [],
        }
        artifacts = [{"type": "plan_file", "uri": "workspace://x/tfplan"}]
        if mode == "plan":
            artifacts.append({"type": "plan_text", "preview": "Plan: 3 to add, 0 to change, 0 to destroy."})
        return InfraExecutionResult(
            execution_id=payload["execution_id"],
            status="succeeded",
            logs=f"[mock] terraform {mode}\nPlan: 3 to add, 0 to change, 0 to destroy.\n",
            artifacts=artifacts,
            outputs=outputs,
            duration_ms=40,
        )


def _register(client, prefix: str = "gcpinfra") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "GCP Infra"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _project_and_topology(client, headers) -> tuple[str, str]:
    pid = client.get("/projects", headers=headers).json()[0]["id"]
    tr = client.post("/topologies", headers=headers, json={**TOPOLOGY_BODY, "project_id": pid})
    assert tr.status_code == 201, tr.text
    return pid, tr.json()["id"]


def _install_runner(monkeypatch) -> _CapturingInfraRunner:
    from app.runtime.infra_runner_client import set_infra_runner_client

    mock = _CapturingInfraRunner()
    set_infra_runner_client(mock)
    return mock


def _gcp_credentials(monkeypatch, tmp_path):
    cred_file = tmp_path / "gcp-sa.json"
    cred_file.write_text(json.dumps({"type": "service_account", "project_id": "my-gcp-project"}))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))
    pub = tmp_path / "gcp-remote-docker-key.pub"
    pub.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtestkey cns-remote-docker\n")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(pub))


def test_create_gcp_docker_vm_deployment(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)

    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-stack",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["provider"] == "gcp"
    assert body["credentials_ref"] == "env:GOOGLE_APPLICATION_CREDENTIALS"


def test_gcp_missing_credentials_ref_fails(client_strict, monkeypatch):
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "no-creds",
            "template_id": "docker-vm",
            "provider": "gcp",
            "variables": GCP_VARS,
        },
    )
    assert r.status_code == 400
    assert "credentials_ref" in r.json()["detail"].lower()


def test_reject_unknown_gcp_variable(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    bad_vars = {**GCP_VARS, "evil_var": "nope"}
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "bad-var",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": bad_vars,
        },
    )
    assert r.status_code == 400
    assert "Unknown variables" in r.json()["detail"]


def test_gcp_validate_and_plan_invokes_terraform(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-plan",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    ).json()
    dep_id = create["id"]

    validate = client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    assert validate.status_code == 200, validate.text
    assert validate.json()["status"] == "validated"

    plan = client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)
    assert plan.status_code == 200, plan.text
    planned = plan.json()
    assert planned["status"] == "awaiting_confirmation"
    summary = planned["plan_summary_json"]
    assert summary["provider"] == "gcp"
    assert summary["machine_type"] == "e2-medium"
    assert summary.get("apply_eligible") is True
    assert summary.get("apply_disabled") is False
    assert summary.get("safety_checklist", {}).get("passed") is True

    tf_calls = [c for c in runner.calls if c.get("execution_type") == "terraform"]
    modes = {c["mode"] for c in tf_calls}
    assert {"validate", "fmt", "plan"}.issubset(modes)
    plan_call = next(c for c in tf_calls if c["mode"] == "plan")
    assert plan_call["template_dir"] == "terraform/gcp/docker_vm"
    assert plan_call.get("plan_only") is True
    assert "GOOGLE_APPLICATION_CREDENTIALS" in plan_call.get("credentials_env", {})


def test_gcp_apply_requires_typed_confirmation(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-no-apply",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    ).json()["id"]
    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    assert confirm.status_code == 400
    assert "APPLY" in confirm.json()["detail"]


def test_gcp_plan_only_destroy_returns_409(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "gcp-no-destroy",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": GCP_VARS,
        },
    ).json()["id"]
    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)

    destroy = client_strict.post(f"/infrastructure-deployments/{dep_id}/destroy", headers=h)
    assert destroy.status_code == 409
    assert "plan-only" in destroy.json()["detail"].lower()


def test_aws_docker_vm_coming_soon(client_strict, monkeypatch):
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "aws-soon",
            "template_id": "docker-vm",
            "provider": "aws",
            "credentials_ref": "env:AWS_PROFILE",
            "variables": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "allowed_ssh_cidr": "203.0.113.0/24",
                "allowed_app_cidr": "203.0.113.0/24",
                "vm_count": 1,
            },
        },
    )
    assert r.status_code == 400
    assert "coming soon" in r.json()["detail"].lower()


def test_resolve_gcp_credentials_env(tmp_path, monkeypatch):
    from app.services.terraform_credentials_service import resolve_terraform_credentials_env

    cred_file = tmp_path / "sa.json"
    cred_file.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))
    env = resolve_terraform_credentials_env("gcp", "env:GOOGLE_APPLICATION_CREDENTIALS")
    assert env["GOOGLE_APPLICATION_CREDENTIALS"] == str(cred_file)

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(ValueError, match="not configured"):
        resolve_terraform_credentials_env("gcp", "env:GOOGLE_APPLICATION_CREDENTIALS")
