"""Terraform execution via Go runner (Step 57C/57D/57E)."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.infrastructure_execution import InfrastructureExecution
from app.runtime.infra_runner_client import get_infra_runner_client
from app.services.infra_apply_safety import is_gcp_docker_vm_apply_eligible
from app.services.infra_security import is_real_cloud_provider, redact_logs
from app.services.infra_template_registry import assert_template_on_disk, get_template, resolve_terraform_dir
from app.services.terraform_credentials_service import (
    redact_credentials_env,
    resolve_terraform_credentials_env,
)


def _uses_persistent_workspace(deployment: InfrastructureDeployment, mode: str) -> bool:
    return is_gcp_docker_vm_apply_eligible(deployment) and mode in {"plan", "apply", "destroy"}


def _plan_only(deployment: InfrastructureDeployment, mode: str) -> bool:
    if not is_real_cloud_provider(deployment.provider):
        return False
    if is_gcp_docker_vm_apply_eligible(deployment) and mode in {"apply", "destroy"}:
        return False
    return True


def _base_payload(
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
    mode: str,
) -> dict[str, Any]:
    template = get_template(deployment.template_id)
    template_dir = resolve_terraform_dir(deployment.template_id, deployment.provider)
    assert_template_on_disk(deployment.template_id, deployment.provider)
    _ = template

    payload: dict[str, Any] = {
        "execution_id": str(execution.id),
        "execution_type": "terraform",
        "template_id": deployment.template_id,
        "template_dir": template_dir,
        "provider": deployment.provider,
        "variables": _stringify_variables(
            {
                **(deployment.variables_json or {}),
                "deployment_name": deployment.name,
            }
        ),
        "deployment_id": str(deployment.id),
        "topology_id": str(deployment.topology_id),
        "plan_only": _plan_only(deployment, mode),
    }

    if _uses_persistent_workspace(deployment, mode):
        payload["workspace_id"] = str(deployment.id)
        payload["preserve_workspace"] = True
    if is_gcp_docker_vm_apply_eligible(deployment) and mode == "apply":
        payload["apply_from_plan"] = True

    if is_real_cloud_provider(deployment.provider):
        cred_env = resolve_terraform_credentials_env(deployment.provider, deployment.credentials_ref)
        payload["credentials_env"] = cred_env
        payload["credentials_ref"] = (deployment.credentials_ref or "").strip()

    return payload


def _stringify_variables(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


def _run(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
    mode: str,
) -> tuple[str, list[dict], dict[str, Any]]:
    execution.mode = mode
    execution.status = "running"
    execution.started_at = datetime.now(UTC)
    db.flush()

    payload = _base_payload(execution=execution, deployment=deployment, mode=mode)
    payload["mode"] = mode
    if payload.get("credentials_env"):
        payload_for_log = {**payload, "credentials_env": redact_credentials_env(payload["credentials_env"])}
    else:
        payload_for_log = payload

    started = time.monotonic()
    result = get_infra_runner_client().run_execution(payload)
    duration_ms = int((time.monotonic() - started) * 1000)

    execution.runner_execution_id = result.execution_id
    execution.duration_ms = duration_ms
    execution.finished_at = datetime.now(UTC)
    execution.logs = redact_logs(result.logs)
    execution.artifact_refs = list(result.artifacts)
    execution.status = "succeeded" if result.status == "succeeded" else "failed"
    db.flush()

    if execution.status != "succeeded":
        err = result.error or f"Terraform {mode} failed"
        if payload.get("credentials_env"):
            err = redact_logs(err)
        raise ValueError(err)

    _ = payload_for_log
    return execution.logs or "", execution.artifact_refs, dict(result.outputs or {})


def execute_validate(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run(db, execution=execution, deployment=deployment, mode="validate")


def execute_fmt(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run(db, execution=execution, deployment=deployment, mode="fmt")


def execute_plan(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    logs, artifacts, outputs = _run(db, execution=execution, deployment=deployment, mode="plan")
    summary = build_plan_summary(deployment, outputs, artifacts, logs)
    artifacts = [*artifacts, {"type": "plan_summary", **summary}]
    return logs, artifacts, outputs


def execute_apply(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run(db, execution=execution, deployment=deployment, mode="apply")


def execute_destroy(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run(db, execution=execution, deployment=deployment, mode="destroy")


def _parse_plan_counts(plan_text: str) -> dict[str, int]:
    counts = {"add": 0, "change": 0, "destroy": 0}
    if not plan_text:
        return counts
    match = re.search(
        r"Plan:\s+(\d+)\s+to add,\s+(\d+)\s+to change,\s+(\d+)\s+to destroy",
        plan_text,
    )
    if match:
        counts["add"] = int(match.group(1))
        counts["change"] = int(match.group(2))
        counts["destroy"] = int(match.group(3))
    return counts


def build_plan_summary(
    deployment: InfrastructureDeployment,
    outputs: dict[str, Any],
    artifacts: list[dict],
    plan_logs: str = "",
) -> dict[str, Any]:
    from app.services.infra_apply_safety import build_apply_safety_checklist

    hosts = outputs.get("hosts") or []
    if isinstance(hosts, str):
        try:
            hosts = json.loads(hosts)
        except json.JSONDecodeError:
            hosts = []
    exposed_ports = outputs.get("exposed_ports") or []
    warnings = outputs.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]

    plan_preview = ""
    for artifact in artifacts:
        if artifact.get("type") == "plan_text":
            plan_preview = str(artifact.get("preview") or "")
            break

    plan_counts = _parse_plan_counts(plan_logs or plan_preview)
    variables = deployment.variables_json or {}
    apply_eligible = is_gcp_docker_vm_apply_eligible(deployment)
    safety_checklist = (
        build_apply_safety_checklist(deployment) if apply_eligible else None
    )

    return {
        "template_id": deployment.template_id,
        "provider": deployment.provider,
        "region": outputs.get("region") or variables.get("region"),
        "zone": outputs.get("zone") or variables.get("zone"),
        "vm_count": outputs.get("vm_count") or len(hosts) or variables.get("vm_count", 1),
        "machine_type": outputs.get("machine_type") or variables.get("machine_type") or variables.get("instance_type"),
        "hosts_preview": hosts[:10],
        "exposed_ports": exposed_ports,
        "firewall_rules": outputs.get("firewall_rules") or [],
        "estimated_resources": outputs.get("estimated_resources") or {},
        "plan_counts": plan_counts,
        "warnings": list(warnings) if isinstance(warnings, list) else [],
        "requires_confirmation": True,
        "apply_disabled": not apply_eligible and is_real_cloud_provider(deployment.provider),
        "apply_eligible": apply_eligible,
        "safety_checklist": safety_checklist,
        "cost_warning": "This may create billable cloud resources." if apply_eligible else None,
        "artifacts_count": len(artifacts),
    }
