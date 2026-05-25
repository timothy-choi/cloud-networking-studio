"""Tests for infrastructure deployments (Step 57C)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

TOPOLOGY_BODY = {
    "name": "Infra Deploy Lab",
    "description": "step 57c",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


@dataclass
class _MockInfraRunner:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_execution(self, payload: dict[str, Any]):
        from app.runtime.infra_runner_client import InfraExecutionResult

        self.calls.append(payload)
        mode = payload.get("mode")
        execution_type = payload.get("execution_type")
        outputs = {
            "vm_count": 1,
            "region": "local",
            "hosts": [
                {
                    "name": "lab-vm-1",
                    "public_ip": "203.0.113.10",
                    "private_ip": "10.0.0.10",
                    "ssh_user": "ubuntu",
                    "ssh_port": 22,
                }
            ],
            "exposed_ports": [22, 80, 443],
        }
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
            logs=f"[mock] terraform {mode}\n",
            artifacts=[{"type": "plan_file", "uri": f"mock://{payload['execution_id']}/plan.out"}],
            outputs=outputs,
            duration_ms=25,
        )


def _register(client, prefix: str = "infra") -> dict[str, str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Infra"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _project_and_topology(client, headers) -> tuple[str, str]:
    pid = client.get("/projects", headers=headers).json()[0]["id"]
    tr = client.post("/topologies", headers=headers, json={**TOPOLOGY_BODY, "project_id": pid})
    assert tr.status_code == 201, tr.text
    return pid, tr.json()["id"]


def _install_mock_runner(monkeypatch):
    from app.runtime.infra_runner_client import set_infra_runner_client

    mock = _MockInfraRunner()
    set_infra_runner_client(mock)
    return mock


def test_list_whitelisted_templates(client_strict):
    h = _register(client_strict)
    r = client_strict.get("/infrastructure/templates", headers=h)
    assert r.status_code == 200
    ids = {item["template_id"] for item in r.json()["items"]}
    assert "local-mock" in ids


def test_create_infra_deployment_plan_and_confirm(client_strict, monkeypatch):
    mock = _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)

    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "lab-infra",
            "template_id": "local-mock",
            "provider": "local",
            "variables": {"region": "local", "vm_count": 1},
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["plan_summary_json"]["vm_count"] == 1
    deployment_id = body["id"]

    execs = client_strict.get(f"/infrastructure-deployments/{deployment_id}/executions", headers=h)
    assert execs.status_code == 200
    assert len(execs.json()["items"]) >= 3
    assert any(item["execution_type"] == "terraform" and item["mode"] == "plan" for item in execs.json()["items"])

    confirm = client_strict.post(
        f"/infrastructure-deployments/{deployment_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    assert confirm.status_code == 200, confirm.text
    applied = confirm.json()
    assert applied["status"] == "succeeded"
    assert len(applied["runtime_targets_json"]) == 1
    assert applied["runtime_targets_json"][0]["target_type"] == "remote_docker"
    assert any(call["mode"] == "apply" for call in mock.calls if call.get("execution_type") == "terraform")


def test_reject_unsupported_template(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={"name": "bad", "template_id": "evil-template", "provider": "local"},
    )
    assert r.status_code == 400


def test_sanitize_sensitive_variables(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    r = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={
            "name": "bad-vars",
            "template_id": "local-mock",
            "provider": "local",
            "variables": {"aws_secret_access_key": "nope"},
        },
    )
    assert r.status_code == 400


def test_destroy_infrastructure_deployment(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    created = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={"name": "destroy-me", "template_id": "local-mock", "provider": "local"},
    ).json()
    client_strict.post(
        f"/infrastructure-deployments/{created['id']}/confirm",
        headers=h,
        json={"confirm": True},
    )
    destroyed = client_strict.post(f"/infrastructure-deployments/{created['id']}/destroy", headers=h)
    assert destroyed.status_code == 200
    assert destroyed.json()["status"] == "destroyed"


def test_ansible_inventory_generation():
    from app.models.infrastructure_deployment import InfrastructureDeployment
    from app.services import ansible_executor_service as ansible_svc

    deployment = InfrastructureDeployment(
        name="lab",
        template_id="local-mock",
        provider="local",
        outputs_json={
            "hosts": [
                {"name": "vm1", "public_ip": "203.0.113.10", "ssh_user": "ubuntu", "ssh_port": 22}
            ]
        },
    )
    inventory = ansible_svc.generate_inventory(deployment)
    hosts = inventory["all"]["children"]["cns_runtime"]["hosts"]
    assert hosts[0]["ansible_host"] == "203.0.113.10"
    preview = ansible_svc.inventory_ini_preview(inventory)
    assert "[cns_runtime]" in preview
    assert "203.0.113.10" in preview
