"""Tests for infra runner HTTP client (Step 57E apply/destroy error handling)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.runtime.infra_runner_client import HttpInfraRunnerClient, InfraRunnerClientError


def _response(status: int, body: dict) -> httpx.Response:
    request = httpx.Request("POST", "http://runner:8090/infra/executions")
    return httpx.Response(status, json=body, request=request)


def test_run_execution_parses_runner_422_as_failed_result():
    payload = {
        "execution_id": "exec-apply-1",
        "execution_type": "terraform",
        "mode": "apply",
        "template_id": "docker-vm",
        "provider": "gcp",
        "workspace_id": "dep-1",
        "preserve_workspace": True,
        "apply_from_plan": True,
        "plan_only": False,
    }
    body = {
        "execution_id": "exec-apply-1",
        "status": "failed",
        "logs": "[infra] stored terraform plan file missing\n",
        "artifacts": [],
        "outputs": {},
        "duration_ms": 12,
        "error": "stored terraform plan file missing",
    }
    transport = MagicMock(spec=httpx.BaseTransport)
    transport.handle_request.return_value = _response(422, body)
    client = HttpInfraRunnerClient("http://runner:8090", transport=transport)

    result = client.run_execution(payload)

    assert result.status == "failed"
    assert result.http_status == 422
    assert result.error == "stored terraform plan file missing"
    assert "plan file missing" in result.logs


def test_run_execution_raises_on_unexpected_http_status():
    transport = MagicMock(spec=httpx.BaseTransport)
    transport.handle_request.return_value = _response(500, {"error": "internal"})
    client = HttpInfraRunnerClient("http://runner:8090", transport=transport)

    with pytest.raises(InfraRunnerClientError, match="HTTP 500"):
        client.run_execution({"execution_id": "x", "execution_type": "terraform", "mode": "apply"})


def test_gcp_apply_payload_fields_match_runner_schema(monkeypatch, tmp_path):
    """Apply payload must include persistent workspace + apply_from_plan fields."""
    import uuid
    from types import SimpleNamespace

    from app.services.terraform_executor_service import _base_payload

    cred_file = tmp_path / "gcp-sa.json"
    cred_file.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred_file))
    pub = tmp_path / "gcp-remote-docker-key.pub"
    pub.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtestkey cns-remote-docker\n")
    monkeypatch.setenv("CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH", str(pub))

    dep_id = uuid.uuid4()
    deployment = SimpleNamespace(
        id=dep_id,
        topology_id=uuid.uuid4(),
        name="gcp-stack",
        template_id="docker-vm",
        provider="gcp",
        status="awaiting_confirmation",
        variables_json={
            "project_id": "p",
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "e2-medium",
            "instance_name": "cns-docker-vm",
            "vm_count": 1,
        },
        credentials_ref="env:GOOGLE_APPLICATION_CREDENTIALS",
    )
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        infrastructure_deployment_id=dep_id,
        execution_type="terraform",
        mode="apply",
        status="queued",
    )

    payload = _base_payload(execution=execution, deployment=deployment, mode="apply")
    payload["mode"] = "apply"

    assert payload["execution_type"] == "terraform"
    assert payload["mode"] == "apply"
    assert payload["template_id"] == "docker-vm"
    assert payload["provider"] == "gcp"
    assert payload["plan_only"] is False
    assert payload["workspace_id"] == str(dep_id)
    assert payload["preserve_workspace"] is True
    assert payload["apply_from_plan"] is True
    assert payload["credentials_ref"] == "env:GOOGLE_APPLICATION_CREDENTIALS"
    assert "ssh_public_key" in payload["variables"]
    assert payload["variables"]["ssh_public_key"].startswith("ssh-ed25519 ")
    assert "GOOGLE_APPLICATION_CREDENTIALS" in payload["credentials_env"]


def test_runner_422_apply_failure_returns_409_not_500(client_strict, monkeypatch, tmp_path):
    """Confirm apply surfaces runner execution failure as 409, not 500."""
    import uuid

    from app.runtime.infra_runner_client import InfraExecutionResult, set_infra_runner_client

    from tests.test_infrastructure_deployments_57e import GCP_VARS, _gcp_credentials
    from tests.test_infrastructure_deployments_57d import _CapturingInfraRunner

    _gcp_credentials(monkeypatch, tmp_path)
    base = _CapturingInfraRunner()

    class _ApplyFailRunner:
        def run_execution(self, payload: dict):
            if payload.get("mode") == "apply":
                return InfraExecutionResult(
                    execution_id=payload["execution_id"],
                    status="failed",
                    logs="stored terraform plan file missing\n",
                    error="stored terraform plan file missing",
                    http_status=422,
                )
            return base.run_execution(payload)

    set_infra_runner_client(_ApplyFailRunner())

    email = f"fail422{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "Fail422"},
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=h,
        json={
            "name": "Fail422",
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
            "name": "gcp-fail",
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
        json={"confirm": True, "confirmation_text": "APPLY"},
    )
    assert confirm.status_code == 409, confirm.text
    detail = confirm.json()["detail"]
    assert "plan file missing" in str(detail).lower()

    dep = client_strict.get(f"/infrastructure-deployments/{dep_id}", headers=h).json()
    assert dep["status"] == "failed"
    assert any(ev["type"] == "apply_failed" for ev in dep["events_json"])
