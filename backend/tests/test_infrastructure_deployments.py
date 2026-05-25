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
    assert body["status"] == "pending"
    deployment_id = body["id"]

    validate = client_strict.post(f"/infrastructure-deployments/{deployment_id}/validate", headers=h)
    assert validate.status_code == 200, validate.text

    plan = client_strict.post(f"/infrastructure-deployments/{deployment_id}/plan", headers=h)
    assert plan.status_code == 200, plan.text
    planned = plan.json()
    assert planned["status"] == "awaiting_confirmation"
    assert planned["plan_summary_json"]["vm_count"] == 1

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
    event_types = [event["type"] for event in applied["events_json"]]
    assert "apply_started" in event_types
    assert "apply_completed" in event_types
    assert "configure_started" in event_types
    assert "configure_completed" in event_types
    assert "runtime_ready" in event_types
    # Mock confirm apply runs in-process; runner is only used for validate/plan.
    assert not any(
        call.get("mode") == "apply" and call.get("execution_type") == "terraform" for call in mock.calls
    )
    execs_after = client_strict.get(f"/infrastructure-deployments/{deployment_id}/executions", headers=h)
    assert execs_after.status_code == 200
    items = execs_after.json()["items"]
    assert any(item["execution_type"] == "terraform" and item["mode"] == "apply" for item in items)
    assert any(item["execution_type"] == "ansible" and item["mode"] == "playbook" for item in items)
    assert any("[mock]" in (item.get("logs") or "") for item in items)

    target_id = applied["runtime_targets_json"][0]["target_id"]
    target = client_strict.get(f"/deployment-targets/{target_id}", headers=h)
    assert target.status_code == 200, target.text
    body = target.json()
    assert body["infrastructure_deployment_id"] == deployment_id
    assert body["config_json"].get("is_mock") is True
    assert body["config_json"].get("workload_apply_disabled") is True
    assert "runtime_target_created" in event_types

    apply_job = client_strict.post(
        f"/topologies/{topo_id}/external-deployment-jobs",
        headers=h,
        json={"target_id": target_id, "mode": "apply"},
    )
    assert apply_job.status_code == 400, apply_job.text
    assert "disabled" in apply_job.json()["detail"].lower()


def test_infra_target_registration_is_idempotent(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    pid, topo_id = _project_and_topology(client_strict, h)
    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={"name": "lab-infra-2", "template_id": "local-mock", "provider": "local"},
    )
    deployment_id = create.json()["id"]
    client_strict.post(f"/infrastructure-deployments/{deployment_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{deployment_id}/plan", headers=h)
    confirm = client_strict.post(
        f"/infrastructure-deployments/{deployment_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    assert confirm.status_code == 200, confirm.text
    target_id = confirm.json()["runtime_targets_json"][0]["target_id"]

    from uuid import UUID

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.infrastructure_deployment import InfrastructureDeployment
    from app.models.user import User
    from app.services import infrastructure_deployment_service as infra_svc

    with SessionLocal() as db:
        deployment = db.get(InfrastructureDeployment, UUID(deployment_id))
        user = db.scalars(select(User).limit(1)).first()
        assert deployment is not None
        assert user is not None
        infra_svc._register_runtime_targets(db, deployment=deployment, actor=user)
        db.commit()

    targets = client_strict.get(f"/projects/{pid}/deployment-targets", headers=h)
    linked = [t for t in targets.json()["items"] if t.get("infrastructure_deployment_id") == deployment_id]
    assert len(linked) == 1
    assert linked[0]["id"] == target_id

    refreshed = client_strict.get(f"/infrastructure-deployments/{deployment_id}", headers=h).json()
    assert any(ev.get("type") == "runtime_target_creation_skipped" for ev in refreshed["events_json"])


def test_delete_infra_created_target_does_not_destroy_infra(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={"name": "keep-infra", "template_id": "local-mock", "provider": "local"},
    )
    deployment_id = create.json()["id"]
    client_strict.post(f"/infrastructure-deployments/{deployment_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{deployment_id}/plan", headers=h)
    confirm = client_strict.post(
        f"/infrastructure-deployments/{deployment_id}/confirm",
        headers=h,
        json={"confirm": True},
    ).json()
    target_id = confirm["runtime_targets_json"][0]["target_id"]
    dr = client_strict.delete(f"/deployment-targets/{target_id}", headers=h)
    assert dr.status_code == 204, dr.text
    infra = client_strict.get(f"/infrastructure-deployments/{deployment_id}", headers=h)
    assert infra.status_code == 200
    assert infra.json()["status"] == "succeeded"


def test_confirm_invalid_status_returns_409(client_strict, monkeypatch):
    _install_mock_runner(monkeypatch)
    h = _register(client_strict)
    _, topo_id = _project_and_topology(client_strict, h)
    create = client_strict.post(
        f"/topologies/{topo_id}/infrastructure-deployments",
        headers=h,
        json={"name": "no-plan", "template_id": "local-mock", "provider": "local"},
    )
    deployment_id = create.json()["id"]
    confirm = client_strict.post(
        f"/infrastructure-deployments/{deployment_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    assert confirm.status_code == 409, confirm.text
    detail = confirm.json()["detail"]
    assert "awaiting_confirmation" in str(detail)


def test_reject_terraform_runtime_target(client_strict):
    h = _register(client_strict)
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    r = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=h,
        json={"name": "bad-infra-target", "target_type": "terraform", "config_json": {}},
    )
    assert r.status_code == 400, r.text
    assert "Infrastructure Deployments" in r.json()["detail"]


def test_reject_ansible_runtime_target(client_strict):
    h = _register(client_strict)
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    r = client_strict.post(
        f"/projects/{pid}/deployment-targets",
        headers=h,
        json={"name": "bad-infra-target", "target_type": "ansible", "config_json": {}},
    )
    assert r.status_code == 400, r.text
    assert "runtime target" in r.json()["detail"].lower()


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
    dep_id = created["id"]
    client_strict.post(f"/infrastructure-deployments/{dep_id}/validate", headers=h)
    client_strict.post(f"/infrastructure-deployments/{dep_id}/plan", headers=h)
    client_strict.post(
        f"/infrastructure-deployments/{dep_id}/confirm",
        headers=h,
        json={"confirm": True},
    )
    destroyed = client_strict.post(f"/infrastructure-deployments/{dep_id}/destroy", headers=h)
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
