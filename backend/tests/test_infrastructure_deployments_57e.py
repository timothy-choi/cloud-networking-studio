"""Tests for Step 57E real GCP docker-vm apply/destroy with safety gates."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services.infra_apply_safety import build_apply_safety_checklist, variables_hash

TOPOLOGY_BODY = {
    "name": "GCP Apply Lab",
    "description": "step 57e",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}

GCP_VARS = {
    "project_id": "my-gcp-project",
    "region": "us-central1",
    "zone": "us-central1-a",
    "machine_type": "e2-medium",
    "network_name": "cns-default",
    "instance_name": "cns-docker-vm",
    "ssh_user": "ubuntu",
    "allowed_ssh_cidr": "203.0.113.0/24",
    "allowed_app_cidr": "203.0.113.0/24",
    "tags": "cns-docker-vm",
    "vm_count": 1,
}

GCP_HOSTS = [
    {
        "name": "cns-docker-vm",
        "public_ip": "203.0.113.55",
        "private_ip": "10.128.0.5",
        "ssh_user": "ubuntu",
        "ssh_port": 22,
    }
]


@dataclass
class _CapturingInfraRunner:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_execution(self, payload: dict[str, Any]):
        from app.runtime.infra_runner_client import InfraExecutionResult

        self.calls.append(payload)
        mode = payload.get("mode")
        execution_type = payload.get("execution_type")
        outputs = {
            "vm_count": 1,
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "e2-medium",
            "instance_name": "cns-docker-vm",
            "public_ip": "203.0.113.55",
            "private_ip": "10.128.0.5",
            "network_name": "cns-default",
            "ssh_user": "ubuntu",
            "exposed_ports": [22, 80, 443],
            "firewall_rules": ["cns-docker-vm-allow-ssh", "cns-docker-vm-allow-app"],
            "estimated_resources": {"compute_instances": 1, "firewall_rules": 2},
            "warnings": [],
            "hosts": [],
        }
        artifacts = [{"type": "plan_file", "uri": "workspace://x/tfplan"}]
        if mode == "plan":
            artifacts.append({"type": "plan_text", "preview": "Plan: 3 to add, 0 to change, 0 to destroy."})
        if mode == "apply":
            outputs["hosts"] = GCP_HOSTS
        if execution_type == "ansible":
            return InfraExecutionResult(
                execution_id=payload["execution_id"],
                status="succeeded",
                logs=f"[mock] ansible {mode}\n",
                artifacts=[{"type": "inventory", "uri": "mock://inventory"}],
                outputs={"inventory": payload.get("inventory") or {}},
                duration_ms=12,
            )
        return InfraExecutionResult(
            execution_id=payload["execution_id"],
            status="succeeded",
            logs=f"[mock] terraform {mode}\nPlan: 3 to add, 0 to change, 0 to destroy.\n",
            artifacts=artifacts,
            outputs=outputs,
            duration_ms=40,
        )


def _register(client, prefix: str = "gcpapply") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "GCP Apply"},
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


def _create_gcp_deployment(client, headers, topo_id, *, variables: dict | None = None) -> str:
    create = client.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=headers,
        json={
            "name": "gcp-stack",
            "template_id": "docker-vm",
            "provider": "gcp",
            "credentials_ref": "env:GOOGLE_APPLICATION_CREDENTIALS",
            "variables": variables or GCP_VARS,
        },
    )
    assert create.status_code == 201, create.text
    return create.json()["id"]


def _plan_gcp(client, headers, dep_id: str) -> dict:
    client.post(f"/infrastructure-deployments/{dep_id}/validate", headers=headers)
    plan = client.post(f"/infrastructure-deployments/{dep_id}/plan", headers=headers)
    assert plan.status_code == 200, plan.text
    return plan.json()


def test_apply_rejected_without_plan(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 409


def test_apply_rejected_if_plan_stale(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    monkeypatch.setattr(
        "app.services.infra_apply_safety.variables_hash",
        lambda _variables: "stale-plan-hash",
    )

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 400
    detail = confirm.json()["detail"]
    assert "stale" in str(detail).lower()


def test_apply_rejected_for_aws(client_strict, monkeypatch):
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "aws-blocked",
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


def test_apply_rejected_for_unsafe_cidr_without_override(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    unsafe_vars = {**GCP_VARS, "allowed_ssh_cidr": "0.0.0.0/0"}
    dep_id = _create_gcp_deployment(client_strict, h, topo_id, variables=unsafe_vars)
    _plan_gcp(client_strict, h, dep_id)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 400
    assert "0.0.0.0/0" in str(confirm.json()["detail"])


def test_gcp_apply_allowed_with_typed_confirmation(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    planned = _plan_gcp(client_strict, h, dep_id)
    assert planned["plan_summary_json"]["apply_eligible"] is True
    assert planned["plan_summary_json"]["safety_checklist"]["passed"] is True

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 200, confirm.text
    applied = confirm.json()
    assert applied["status"] == "succeeded"
    assert applied["outputs_json"]["public_ip"] == "203.0.113.55"
    assert len(applied["runtime_targets_json"]) == 1
    assert applied["runtime_targets_json"][0]["host"] == "203.0.113.55"

    apply_call = next(
        c for c in runner.calls if c.get("execution_type") == "terraform" and c.get("mode") == "apply"
    )
    assert apply_call.get("apply_from_plan") is True
    assert apply_call.get("preserve_workspace") is True
    assert apply_call.get("workspace_id") == dep_id
    assert apply_call.get("plan_only") is False


def test_apply_requires_apply_confirmation_text(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "yes"},
    )
    assert confirm.status_code == 400
    assert "APPLY" in confirm.json()["detail"]


def test_gcp_destroy_runs_for_applied_stack(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)
    client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )

    destroy = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/destroy",
        headers=h,
        json={"confirmation_text": "DESTROY"},
    )
    assert destroy.status_code == 200, destroy.text
    assert destroy.json()["status"] == "destroyed"
    destroy_call = next(
        c for c in runner.calls if c.get("execution_type") == "terraform" and c.get("mode") == "destroy"
    )
    assert destroy_call.get("preserve_workspace") is True


def test_destroy_idempotent(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)
    client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    client_strict.post(
        f"/infrastructure-deployments/{dep_id}/destroy",
        headers=h,
        json={"confirmation_text": "DESTROY"},
    )
    again = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/destroy",
        headers=h,
        json={"confirmation_text": "DESTROY"},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "destroyed"


def test_gcp_plan_only_destroy_still_blocked(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    destroy = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/destroy",
        headers=h,
        json={"confirmation_text": "DESTROY"},
    )
    assert destroy.status_code == 409


def test_local_mock_still_works(client_strict, monkeypatch):
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="mock57e")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "mock-stack",
            "template_id": "local-mock",
            "provider": "local",
            "variables": {"region": "local", "vm_count": 1},
        },
    ).json()["id"]
    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)
    confirm = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "succeeded"
    assert len(confirm.json()["runtime_targets_json"]) == 1


def test_build_apply_safety_checklist_unit(monkeypatch, tmp_path):
    from app.models.infrastructure_deployment import InfrastructureDeployment

    pub = tmp_path / "gcp-remote-docker-key.pub"
    pub.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtestkey cns-remote-docker\n")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(pub))

    dep = InfrastructureDeployment(
        project_id=uuid.uuid4(),
        topology_id=uuid.uuid4(),
        name="unit",
        template_id="docker-vm",
        provider="gcp",
        status="awaiting_confirmation",
        variables_json=GCP_VARS,
        credentials_ref="env:GOOGLE_APPLICATION_CREDENTIALS",
        state_metadata_json={
            "plan_execution_id": str(uuid.uuid4()),
            "variables_hash": variables_hash(GCP_VARS),
        },
    )
    checklist = build_apply_safety_checklist(dep)
    assert checklist["passed"] is True
    assert any(item["name"] == "cost_warning" for item in checklist["items"])
