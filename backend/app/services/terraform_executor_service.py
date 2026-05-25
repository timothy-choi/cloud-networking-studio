"""Terraform execution via Go runner (Step 57C)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.infrastructure_execution import InfrastructureExecution
from app.runtime.infra_runner_client import get_infra_runner_client
from app.services.infra_security import redact_logs
from app.services.infra_template_registry import assert_template_on_disk, get_template


def _base_payload(
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> dict[str, Any]:
    template = get_template(deployment.template_id)
    assert_template_on_disk(deployment.template_id)
    _ = template
    return {
        "execution_id": str(execution.id),
        "execution_type": "terraform",
        "template_id": deployment.template_id,
        "provider": deployment.provider,
        "variables": _stringify_variables(
            {
                **(deployment.variables_json or {}),
                "deployment_name": deployment.name,
            }
        ),
        "deployment_id": str(deployment.id),
        "topology_id": str(deployment.topology_id),
    }


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

    payload = _base_payload(execution=execution, deployment=deployment)
    payload["mode"] = mode
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
        raise ValueError(result.error or f"Terraform {mode} failed")

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
    summary = build_plan_summary(deployment, outputs, artifacts)
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


def build_plan_summary(
    deployment: InfrastructureDeployment,
    outputs: dict[str, Any],
    artifacts: list[dict],
) -> dict[str, Any]:
    hosts = outputs.get("hosts") or []
    if isinstance(hosts, str):
        try:
            hosts = json.loads(hosts)
        except json.JSONDecodeError:
            hosts = []
    exposed_ports = outputs.get("exposed_ports") or []
    return {
        "template_id": deployment.template_id,
        "provider": deployment.provider,
        "region": outputs.get("region") or deployment.variables_json.get("region"),
        "vm_count": outputs.get("vm_count") or len(hosts) or deployment.variables_json.get("vm_count", 1),
        "hosts_preview": hosts[:10],
        "exposed_ports": exposed_ports,
        "requires_confirmation": True,
        "artifacts_count": len(artifacts),
    }
