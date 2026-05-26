"""Tests for Step 57F GCP external infra release candidate hardening."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from tests.test_infrastructure_deployments_57e import (
    GCP_VARS,
    _CapturingInfraRunner,
    _create_gcp_deployment,
    _gcp_credentials,
    _install_runner,
    _plan_gcp,
    _project_and_topology,
    _register,
)


def test_configuration_failed_when_ansible_fails(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="cfgfail")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service.ansible_svc.execute_configure",
        side_effect=ValueError("SSH connection timed out"),
    ):
        confirm = client_strict.post(
            f"/infrastructure-deployments/{dep_id}/confirm",
            headers=h,
            json={"confirm": True, "confirmation_text": "APPLY"},
        )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["status"] == "configuration_failed"
    assert "SSH connection timed out" in (body.get("error_message") or "")
    assert any(ev["type"] == "configure_failed" for ev in body["events_json"])


def test_retry_configuration_recovers(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="cfgretry")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service.ansible_svc.execute_configure",
        side_effect=ValueError("temporary configure failure"),
    ):
        client_strict.post(
            f"/infrastructure-deployments/{dep_id}/confirm",
            headers=h,
            json={"confirm": True, "confirmation_text": "APPLY"},
        )

    retry = client_strict.post(f"/infrastructure-deployments/{dep_id}/retry-configure", headers=h)
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "succeeded"
    assert len(retry.json()["runtime_targets_json"]) >= 1


def test_destroy_from_configuration_failed(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _CapturingInfraRunner()
    from app.runtime.infra_runner_client import set_infra_runner_client

    set_infra_runner_client(runner)
    h = _register(client_strict, prefix="destroycfg")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service.ansible_svc.execute_configure",
        side_effect=ValueError("configure failed"),
    ):
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
    assert any(c.get("mode") == "destroy" for c in runner.calls if c.get("execution_type") == "terraform")


def test_registration_failed_when_no_targets(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="regfail")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service._register_runtime_targets",
        return_value=[],
    ):
        confirm = client_strict.post(
            f"/infrastructure-deployments/{dep_id}/confirm",
            headers=h,
            json={"confirm": True, "confirmation_text": "APPLY"},
        )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["status"] == "registration_failed"
    assert body["runtime_targets_json"] == []


def test_destroy_from_registration_failed(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="destroyreg")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service._register_runtime_targets",
        return_value=[],
    ):
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
    assert destroy.status_code == 200
    assert destroy.json()["status"] == "destroyed"


def test_destroy_idempotent_from_destroyed(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="idempotent57f")
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


def test_retry_configure_rejects_wrong_status(client_strict, monkeypatch, tmp_path):
    _gcp_credentials(monkeypatch, tmp_path)
    _install_runner(monkeypatch)
    h = _register(client_strict, prefix="retrybad")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    retry = client_strict.post(f"/infrastructure-deployments/{dep_id}/retry-configure", headers=h)
    assert retry.status_code == 409


def test_destroy_from_failed_with_applied_metadata(client_strict, monkeypatch, tmp_path):
    """Partial apply metadata should still allow cleanup destroy."""
    _gcp_credentials(monkeypatch, tmp_path)
    runner = _CapturingInfraRunner()
    from app.runtime.infra_runner_client import set_infra_runner_client

    set_infra_runner_client(runner)
    h = _register(client_strict, prefix="destroyfail")
    _, topo_id = _project_and_topology(client_strict, h)
    dep_id = _create_gcp_deployment(client_strict, h, topo_id)
    _plan_gcp(client_strict, h, dep_id)

    with patch(
        "app.services.infrastructure_deployment_service.ansible_svc.execute_configure",
        side_effect=ValueError("configure failed"),
    ):
        client_strict.post(
            f"/infrastructure-deployments/{dep_id}/confirm",
            headers=h,
            json={"confirm": True, "confirmation_text": "APPLY"},
        )

    dep = client_strict.get(f"/infrastructure-deployments/{dep_id}", headers=h).json()
    assert dep["status"] == "configuration_failed"
    assert dep["state_metadata_json"].get("applied_at")

    destroy = client_strict.post(
        f"/infrastructure-deployments/{dep_id}/destroy",
        headers=h,
        json={"confirmation_text": "DESTROY"},
    )
    assert destroy.status_code == 200, destroy.text
    assert destroy.json()["status"] == "destroyed"
