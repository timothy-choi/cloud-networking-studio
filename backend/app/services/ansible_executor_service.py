"""Ansible execution via Go runner (Step 57C)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.infrastructure_execution import InfrastructureExecution
from app.runtime.infra_runner_client import InfraRunnerClientError, get_infra_runner_client
from app.services.infra_security import redact_logs
from app.services.infra_template_registry import assert_playbook_on_disk, get_playbook, get_template


def generate_inventory(deployment: InfrastructureDeployment) -> dict[str, Any]:
    """Build Ansible inventory from terraform outputs."""
    hosts = deployment.outputs_json.get("hosts") or []
    if isinstance(hosts, str):
        try:
            hosts = json.loads(hosts)
        except json.JSONDecodeError:
            hosts = []
    inventory_hosts = []
    for host in hosts:
        if not isinstance(host, dict):
            continue
        inventory_hosts.append(
            {
                "name": host.get("name"),
                "ansible_host": host.get("public_ip") or host.get("private_ip"),
                "ansible_user": host.get("ssh_user") or "ubuntu",
                "ansible_port": host.get("ssh_port") or 22,
            }
        )
    return {
        "all": {
            "children": {
                "cns_runtime": {
                    "hosts": inventory_hosts,
                }
            }
        }
    }


def inventory_ini_preview(inventory: dict[str, Any]) -> str:
    lines = ["[cns_runtime]"]
    for host in inventory.get("all", {}).get("children", {}).get("cns_runtime", {}).get("hosts", []):
        name = host.get("name") or "host"
        ansible_host = host.get("ansible_host") or "127.0.0.1"
        ansible_user = host.get("ansible_user") or "ubuntu"
        ansible_port = host.get("ansible_port") or 22
        lines.append(
            f"{name} ansible_host={ansible_host} ansible_user={ansible_user} ansible_port={ansible_port}"
        )
    return "\n".join(lines) + "\n"


def _run_playbooks(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
    mode: str,
) -> tuple[str, list[dict], dict[str, Any]]:
    template = get_template(deployment.template_id)
    inventory = deployment.inventory_json or generate_inventory(deployment)
    playbook_paths = []
    for playbook_id in template.ansible_playbooks:
        playbook_paths.append(get_playbook(playbook_id).filename)

    execution.mode = mode
    execution.status = "running"
    execution.started_at = datetime.now(UTC)
    db.flush()

    payload = {
        "execution_id": str(execution.id),
        "execution_type": "ansible",
        "mode": mode,
        "template_id": deployment.template_id,
        "provider": deployment.provider,
        "inventory": inventory,
        "inventory_ini": inventory_ini_preview(inventory),
        "playbook_paths": playbook_paths,
        "deployment_id": str(deployment.id),
        "topology_id": str(deployment.topology_id),
    }
    started = time.monotonic()
    try:
        result = get_infra_runner_client().run_execution(payload)
    except InfraRunnerClientError as exc:
        execution.finished_at = datetime.now(UTC)
        execution.status = "failed"
        err_msg = redact_logs(exc.detail or exc.message)
        execution.logs = err_msg
        db.flush()
        raise ValueError(err_msg) from exc
    duration_ms = int((time.monotonic() - started) * 1000)

    execution.runner_execution_id = result.execution_id
    execution.duration_ms = duration_ms or result.duration_ms
    execution.finished_at = datetime.now(UTC)
    execution.logs = redact_logs(result.logs)
    execution.artifact_refs = list(result.artifacts)
    execution.status = "succeeded" if result.status == "succeeded" else "failed"
    db.flush()

    if execution.status != "succeeded":
        err = result.error or f"Ansible {mode} failed"
        raise ValueError(redact_logs(err))

    outputs = dict(result.outputs or {})
    outputs["inventory"] = inventory
    return execution.logs or "", execution.artifact_refs, outputs


def execute_inventory(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    inventory = generate_inventory(deployment)
    execution.status = "running"
    execution.started_at = datetime.now(UTC)
    logs = inventory_ini_preview(inventory)
    execution.logs = redact_logs(logs)
    execution.artifact_refs = [{"type": "inventory", "format": "ini", "preview": logs[:4000]}]
    execution.status = "succeeded"
    execution.finished_at = datetime.now(UTC)
    db.flush()
    return execution.logs, execution.artifact_refs, {"inventory": inventory}


def execute_validate(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run_playbooks(db, execution=execution, deployment=deployment, mode="validate")


def execute_configure(
    db: Session,
    *,
    execution: InfrastructureExecution,
    deployment: InfrastructureDeployment,
) -> tuple[str, list[dict], dict[str, Any]]:
    return _run_playbooks(db, execution=execution, deployment=deployment, mode="playbook")
