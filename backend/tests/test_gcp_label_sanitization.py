"""Tests for GCP label and resource name sanitization."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.infra_security import (
    gcp_terraform_label_variables,
    sanitize_gcp_label_value,
    sanitize_gcp_resource_name,
    validate_template_variables,
)
from app.services.terraform_executor_service import _base_payload
from app.services.topology_placement_planner_service import build_generate_deployment_payload


def test_sanitize_gcp_label_value_imported_infra_name():
    assert sanitize_gcp_label_value("test1 (imported)-infra") == "test1-imported-infra"


def test_sanitize_gcp_label_value_collapses_and_trims():
    assert sanitize_gcp_label_value("  My Stack (v2)  ") == "my-stack-v2"


def test_sanitize_gcp_label_value_truncates_long_names():
    raw = "a" + "b" * 80 + " (imported)"
    result = sanitize_gcp_label_value(raw)
    assert len(result) <= 63
    assert result[0].isalpha()
    assert result[-1].isalnum()
    assert result.startswith("a")


def test_sanitize_gcp_resource_name_uses_cns_prefix():
    assert sanitize_gcp_resource_name("test1 (imported)").startswith("cns-")
    assert sanitize_gcp_resource_name("test1 (imported)").endswith("imported")


def test_gcp_terraform_label_variables_sanitizes_all_labels():
    labels = gcp_terraform_label_variables(
        deployment_name="test1 (imported)-infra",
        template_id="docker-vm",
        provider="gcp",
    )
    assert labels == {
        "deployment_name": "test1-imported-infra",
        "cns_template": "docker-vm",
        "cns_provider": "gcp",
    }


def test_terraform_payload_uses_sanitized_labels(monkeypatch, tmp_path):
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
        name="test1 (imported)-infra",
        template_id="docker-vm",
        provider="gcp",
        status="awaiting_confirmation",
        variables_json={
            "project_id": "my-gcp-project",
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "e2-micro",
            "instance_name": "cns-test1-imported",
            "vm_count": 1,
            "network_name": "default",
            "allowed_ssh_cidr": "203.0.113.0/24",
            "allowed_app_cidr": "203.0.113.0/24",
            "tags": "cns-docker-vm",
            "ssh_user": "ubuntu",
        },
        credentials_ref="env:GOOGLE_APPLICATION_CREDENTIALS",
    )
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        infrastructure_deployment_id=dep_id,
        execution_type="terraform",
        mode="plan",
        status="queued",
    )

    from app.services.terraform_credentials_service import resolve_terraform_credentials_env

    payload = _base_payload(
        execution=execution,
        deployment=deployment,
        mode="plan",
        credentials_env=resolve_terraform_credentials_env("gcp", deployment.credentials_ref),
    )
    assert payload["variables"]["deployment_name"] == "test1-imported-infra"
    assert payload["variables"]["cns_template"] == "docker-vm"
    assert payload["variables"]["cns_provider"] == "gcp"
    validate_template_variables(
        "docker-vm",
        "gcp",
        {k: v for k, v in payload["variables"].items() if k != "ssh_public_key"},
    )


def test_build_generate_deployment_payload_keeps_display_name_and_sanitizes_variables():
    topo = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="test1 (imported)",
        nodes=[
            SimpleNamespace(
                id=uuid.uuid4(),
                name="web",
                node_type=SimpleNamespace(value="host"),
                image="nginx:alpine",
                config={"resource_cpu": 0.5, "resource_memory_mb": 512, "resource_disk_gb": 5},
            ),
        ],
        links=[],
    )
    draft = build_generate_deployment_payload(topo, db=None)  # type: ignore[arg-type]
    assert draft["name"] == "test1 (imported)-infra"
    assert draft["variables"]["deployment_name"] == "test1-imported"
    assert draft["variables"]["cns_template"] == "docker-vm"
    assert draft["variables"]["cns_provider"] == "gcp"
    assert draft["variables"]["instance_name"].startswith("cns-")
