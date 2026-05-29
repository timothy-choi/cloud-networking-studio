"""Tests for infrastructure deployment phase flags and recovery helpers."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services import infra_deployment_phases as phases


def _deployment(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "status": "awaiting_confirmation",
        "template_id": "docker-vm",
        "provider": "gcp",
        "state_metadata_json": {
            "workspace_id": "dep-123",
            "plan_file": "tfplan",
            "phases": {},
        },
        "events_json": [],
        "outputs_json": {},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_can_confirm_apply_blocks_after_apply_started():
    dep = _deployment(
        state_metadata_json={"phases": {phases.PHASE_TERRAFORM_APPLY_STARTED: True}},
    )
    ok, reason = phases.can_confirm_apply(dep)
    assert ok is False
    assert "Terraform already applied" in (reason or "")


def test_can_destroy_from_configuring_when_apply_completed():
    dep = _deployment(
        status="configuring",
        state_metadata_json={
            "terraform_apply_completed": True,
            "workspace_id": "dep-123",
            "phases": {phases.PHASE_TERRAFORM_APPLY_COMPLETED: True},
        },
    )
    assert phases.can_destroy_deployment(dep, is_mock=False) is True


def test_can_retry_configuration_requires_completed_apply():
    dep = _deployment(
        status="configuration_failed",
        state_metadata_json={"phases": {phases.PHASE_TERRAFORM_APPLY_COMPLETED: True}, "terraform_apply_completed": True},
    )
    assert phases.can_retry_configuration(dep) is True

    pending = _deployment(status="configuration_failed", state_metadata_json={"phases": {}})
    assert phases.can_retry_configuration(pending) is False


def test_build_phase_checklist_marks_completed_apply():
    dep = _deployment(
        status="configuration_failed",
        state_metadata_json={
            "phases": {
                phases.PHASE_TERRAFORM_APPLY_COMPLETED: True,
                phases.PHASE_TERRAFORM_OUTPUTS_CAPTURED: True,
                phases.PHASE_CONFIGURATION_STARTED: True,
            }
        },
        events_json=[{"type": "configure_failed", "message": "timeout"}],
    )
    checklist = phases.build_phase_checklist(dep)
    by_name = {item["name"]: item["status"] for item in checklist}
    assert by_name["terraform_apply"] == "completed"
    assert by_name["outputs_captured"] == "completed"
    assert by_name["host_configuration"] == "failed"


def test_enrich_state_metadata_adds_recovery_message():
    dep = _deployment(
        status="configuration_failed",
        state_metadata_json={"phases": {phases.PHASE_TERRAFORM_APPLY_COMPLETED: True}, "terraform_apply_completed": True},
    )
    meta = phases.enrich_state_metadata(dep)
    assert meta["recovery_message"] == phases.RECOVERY_MESSAGE
    assert isinstance(meta["phase_checklist"], list)
