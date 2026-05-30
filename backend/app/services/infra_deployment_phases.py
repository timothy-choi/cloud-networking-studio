"""Phase flags and recovery helpers for infrastructure deployments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.infrastructure_deployment import InfrastructureDeployment

PHASE_TERRAFORM_APPLY_STARTED = "terraform_apply_started"
PHASE_TERRAFORM_APPLY_COMPLETED = "terraform_apply_completed"
PHASE_TERRAFORM_OUTPUTS_CAPTURED = "terraform_outputs_captured"
PHASE_SSH_READINESS_STARTED = "ssh_readiness_started"
PHASE_SSH_READINESS_COMPLETED = "ssh_readiness_completed"
PHASE_CONFIGURATION_STARTED = "configuration_started"
PHASE_CONFIGURATION_COMPLETED = "configuration_completed"
PHASE_RUNTIME_TARGET_REGISTERED = "runtime_target_registered"
PHASE_DESTROY_STARTED = "destroy_started"
PHASE_DESTROY_COMPLETED = "destroy_completed"

ALL_PHASE_FLAGS = (
    PHASE_TERRAFORM_APPLY_STARTED,
    PHASE_TERRAFORM_APPLY_COMPLETED,
    PHASE_TERRAFORM_OUTPUTS_CAPTURED,
    PHASE_SSH_READINESS_STARTED,
    PHASE_SSH_READINESS_COMPLETED,
    PHASE_CONFIGURATION_STARTED,
    PHASE_CONFIGURATION_COMPLETED,
    PHASE_RUNTIME_TARGET_REGISTERED,
    PHASE_DESTROY_STARTED,
    PHASE_DESTROY_COMPLETED,
)

RECOVERY_MESSAGE = (
    "Terraform created cloud resources, but configuration did not finish. "
    "Retry configuration or destroy infrastructure."
)

APPLY_ALREADY_COMPLETED_MESSAGE = (
    "Terraform already applied. Retry configuration or destroy infrastructure."
)

STALE_PLAN_AFTER_APPLY_MESSAGE = (
    "Terraform state changed after plan. Retry configuration or destroy infrastructure."
)

NON_APPLYABLE_STATUSES = frozenset(
    {
        "applying",
        "configuring",
        "configuration_failed",
        "registration_failed",
        "succeeded",
        "apply_partial",
        "configuration_timeout",
        "destroying",
        "destroyed",
        "destroy_failed",
    }
)

DESTROYABLE_STATUSES = frozenset(
    {
        "succeeded",
        "configuration_failed",
        "registration_failed",
        "failed",
        "applying",
        "configuring",
        "apply_partial",
        "configuration_timeout",
        "destroy_failed",
    }
)

RETRY_CONFIGURATION_STATUSES = frozenset(
    {
        "configuration_failed",
        "registration_failed",
        "applying",
        "configuring",
        "apply_partial",
        "configuration_timeout",
    }
)


def get_phases(deployment: InfrastructureDeployment) -> dict[str, bool]:
    meta = deployment.state_metadata_json or {}
    raw = meta.get("phases") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): bool(value) for key, value in raw.items()}


def _phase_true(deployment: InfrastructureDeployment, phase: str) -> bool:
    return get_phases(deployment).get(phase) is True


def mark_phases(
    deployment: InfrastructureDeployment,
    *,
    flush: bool = False,
    db: Session | None = None,
    **flags: bool,
) -> None:
    meta = dict(deployment.state_metadata_json or {})
    phases = dict(meta.get("phases") or {})
    for key, value in flags.items():
        phases[key] = bool(value)
        if value:
            phases[f"{key}_at"] = datetime.now(UTC).isoformat()
        elif f"{key}_at" in phases and not value:
            phases.pop(f"{key}_at", None)
    meta["phases"] = phases
    deployment.state_metadata_json = meta
    if flush and db is not None:
        db.flush()


def workspace_metadata(deployment: InfrastructureDeployment) -> dict[str, str]:
    meta = deployment.state_metadata_json or {}
    workspace_id = str(meta.get("workspace_id") or deployment.id)
    return {
        "workspace_id": workspace_id,
        "workspace": str(meta.get("workspace") or f"cns-infra-{str(deployment.id)[:8]}"),
        "plan_file": str(meta.get("plan_file") or "tfplan"),
        "terraform_workspace_path": str(meta.get("terraform_workspace_path") or workspace_id),
    }


def persist_workspace_metadata(deployment: InfrastructureDeployment) -> None:
    meta = dict(deployment.state_metadata_json or {})
    meta.update(workspace_metadata(deployment))
    deployment.state_metadata_json = meta


def has_terraform_apply_started(deployment: InfrastructureDeployment) -> bool:
    meta = deployment.state_metadata_json or {}
    return bool(
        _phase_true(deployment, PHASE_TERRAFORM_APPLY_STARTED)
        or meta.get("terraform_apply_started")
    )


def has_terraform_apply_completed(deployment: InfrastructureDeployment) -> bool:
    meta = deployment.state_metadata_json or {}
    return bool(
        _phase_true(deployment, PHASE_TERRAFORM_APPLY_COMPLETED)
        or meta.get("terraform_apply_completed")
        or meta.get("applied_at")
        or meta.get("apply_execution_id")
    )


def has_terraform_resources(deployment: InfrastructureDeployment) -> bool:
    return has_terraform_apply_started(deployment) or has_terraform_apply_completed(deployment)


def has_terraform_workspace(deployment: InfrastructureDeployment) -> bool:
    meta = deployment.state_metadata_json or {}
    return bool(meta.get("workspace_id") or meta.get("plan_file") or meta.get("terraform_workspace_path"))


def can_confirm_apply(deployment: InfrastructureDeployment) -> tuple[bool, str | None]:
    if has_terraform_apply_completed(deployment):
        return False, APPLY_ALREADY_COMPLETED_MESSAGE
    if has_terraform_apply_started(deployment):
        return False, APPLY_ALREADY_COMPLETED_MESSAGE
    if deployment.status in NON_APPLYABLE_STATUSES:
        return False, APPLY_ALREADY_COMPLETED_MESSAGE
    if deployment.status != "awaiting_confirmation":
        return False, f"Deployment must be awaiting_confirmation (current: {deployment.status})"
    return True, None


def can_retry_configuration(deployment: InfrastructureDeployment) -> bool:
    if not has_terraform_apply_completed(deployment):
        return False
    return deployment.status in RETRY_CONFIGURATION_STATUSES


def can_destroy_deployment(
    deployment: InfrastructureDeployment,
    *,
    is_mock: bool,
) -> bool:
    if deployment.status in {"destroyed", "destroying"}:
        return True
    if is_mock:
        return deployment.status == "succeeded"
    if not has_terraform_resources(deployment):
        return False
    return deployment.status in DESTROYABLE_STATUSES or has_terraform_apply_completed(deployment)


def configuration_failure_status(*, timed_out: bool = False) -> str:
    return "configuration_timeout" if timed_out else "configuration_failed"


def configuration_job_status(deployment: InfrastructureDeployment) -> str | None:
    meta = deployment.state_metadata_json or {}
    value = meta.get("configuration_job_status")
    return str(value) if value else None


def is_configuration_job_active(deployment: InfrastructureDeployment) -> bool:
    return configuration_job_status(deployment) in {"queued", "running"}


def build_phase_checklist(deployment: InfrastructureDeployment) -> list[dict[str, Any]]:
    phases = get_phases(deployment)
    status = deployment.status
    event_types = {ev.get("type") for ev in (deployment.events_json or []) if isinstance(ev, dict)}

    def phase_status(
        completed_flag: str,
        *,
        started_flag: str | None = None,
        failed: bool = False,
        running: bool = False,
    ) -> str:
        if failed:
            return "failed"
        if phases.get(completed_flag):
            return "completed"
        if running or (started_flag and phases.get(started_flag)):
            return "running"
        return "pending"

    terraform_failed = status == "failed" and "apply_failed" in event_types
    config_failed = status in {"configuration_failed", "configuration_timeout", "registration_failed"} or (
        "configure_failed" in event_types
    )

    config_job_active = is_configuration_job_active(deployment)

    return [
        {
            "name": "terraform_apply",
            "label": "Terraform apply",
            "status": phase_status(
                PHASE_TERRAFORM_APPLY_COMPLETED,
                started_flag=PHASE_TERRAFORM_APPLY_STARTED,
                failed=terraform_failed and not phases.get(PHASE_TERRAFORM_APPLY_COMPLETED),
                running=status == "applying" and not phases.get(PHASE_TERRAFORM_APPLY_COMPLETED),
            ),
        },
        {
            "name": "outputs_captured",
            "label": "Outputs captured",
            "status": phase_status(
                PHASE_TERRAFORM_OUTPUTS_CAPTURED,
                failed=config_failed and has_terraform_apply_completed(deployment) and not phases.get(PHASE_TERRAFORM_OUTPUTS_CAPTURED),
            ),
        },
        {
            "name": "ssh_readiness",
            "label": "SSH readiness",
            "status": phase_status(
                PHASE_SSH_READINESS_COMPLETED,
                started_flag=PHASE_SSH_READINESS_STARTED,
                failed="ssh_readiness_failed" in event_types,
                running=(
                    (phases.get(PHASE_SSH_READINESS_STARTED) and not phases.get(PHASE_SSH_READINESS_COMPLETED))
                    or (
                        status == "configuring"
                        and has_terraform_apply_completed(deployment)
                        and config_job_active
                        and not phases.get(PHASE_SSH_READINESS_COMPLETED)
                    )
                ),
            ),
        },
        {
            "name": "host_configuration",
            "label": "Host configuration",
            "status": phase_status(
                PHASE_CONFIGURATION_COMPLETED,
                started_flag=PHASE_CONFIGURATION_STARTED,
                failed=config_failed,
                running=(
                    status in {"configuring", "applying"}
                    and phases.get(PHASE_CONFIGURATION_STARTED)
                    and not phases.get(PHASE_CONFIGURATION_COMPLETED)
                )
                or (
                    status == "configuring"
                    and has_terraform_apply_completed(deployment)
                    and config_job_active
                    and phases.get(PHASE_SSH_READINESS_COMPLETED)
                    and not phases.get(PHASE_CONFIGURATION_COMPLETED)
                ),
            ),
        },
        {
            "name": "runtime_target_registration",
            "label": "Runtime target registration",
            "status": phase_status(
                PHASE_RUNTIME_TARGET_REGISTERED,
                failed=status == "registration_failed" or "registration_failed" in event_types,
                running=phases.get(PHASE_CONFIGURATION_COMPLETED) and not phases.get(PHASE_RUNTIME_TARGET_REGISTERED) and status not in {"succeeded", "registration_failed"},
            ),
        },
    ]


def enrich_state_metadata(deployment: InfrastructureDeployment) -> dict[str, Any]:
    meta = dict(deployment.state_metadata_json or {})
    meta["phase_checklist"] = build_phase_checklist(deployment)
    job_status = configuration_job_status(deployment)
    if job_status:
        meta["configuration_job_status"] = job_status
    queued_at = meta.get("configuration_queued_at")
    if queued_at:
        meta["configuration_queued_at"] = queued_at
    if has_terraform_apply_completed(deployment) and deployment.status in {
        "configuration_failed",
        "configuration_timeout",
        "apply_partial",
        "configuring",
        "applying",
        "registration_failed",
    }:
        meta["recovery_message"] = RECOVERY_MESSAGE
    return meta
