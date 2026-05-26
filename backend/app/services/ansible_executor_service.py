"""Ansible execution via Go runner (Step 57C)."""

from __future__ import annotations

import json
import shlex
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.infrastructure_execution import InfrastructureExecution
from app.runtime.infra_runner_client import InfraRunnerClientError, get_infra_runner_client
from app.services.infra_apply_safety import is_gcp_docker_vm_apply_eligible
from app.services.infra_security import redact_logs
from app.services.infra_ssh_readiness import (
    REMOTE_DOCKER_SSH_CREDENTIALS_REF,
    ansible_ssh_common_args,
    resolve_inventory_hosts,
)
from app.services.infra_template_registry import assert_playbook_on_disk, get_playbook, get_template
from app.services.remote_credentials_service import resolve_ssh_key_path


def _ephemeral_vm_inventory_vars(deployment: InfrastructureDeployment) -> dict[str, Any]:
    if not is_gcp_docker_vm_apply_eligible(deployment):
        return {}
    try:
        private_key_file = resolve_ssh_key_path(REMOTE_DOCKER_SSH_CREDENTIALS_REF)
    except ValueError:
        private_key_file = None
    vars_out: dict[str, Any] = {
        "ansible_host_key_checking": False,
        "ansible_ssh_common_args": ansible_ssh_common_args(deployment.id),
    }
    if private_key_file:
        vars_out["ansible_ssh_private_key_file"] = private_key_file
    return vars_out


def generate_inventory(deployment: InfrastructureDeployment) -> dict[str, Any]:
    """Build Ansible inventory from terraform outputs."""
    ephemeral_vars = _ephemeral_vm_inventory_vars(deployment)
    inventory_hosts = []
    for host in resolve_inventory_hosts(deployment):
        inventory_hosts.append(
            {
                "name": host.get("name"),
                "ansible_host": host.get("public_ip"),
                "ansible_user": host.get("ssh_user") or "ubuntu",
                "ansible_port": host.get("ssh_port") or 22,
                **ephemeral_vars,
            }
        )
    return {
        "all": {
            "children": {
                "cns_runtime": {
                    "hosts": inventory_hosts,
                    "vars": ephemeral_vars,
                }
            }
        }
    }


def inventory_ini_preview(inventory: dict[str, Any]) -> str:
    lines = ["[cns_runtime]"]
    group_vars = (
        inventory.get("all", {}).get("children", {}).get("cns_runtime", {}).get("vars") or {}
    )
    for host in inventory.get("all", {}).get("children", {}).get("cns_runtime", {}).get("hosts", []):
        name = host.get("name") or "host"
        ansible_host = host.get("ansible_host") or "127.0.0.1"
        ansible_user = host.get("ansible_user") or "ubuntu"
        ansible_port = host.get("ansible_port") or 22
        parts = [
            name,
            f"ansible_host={ansible_host}",
            f"ansible_user={ansible_user}",
            f"ansible_port={ansible_port}",
        ]
        merged = {**group_vars, **{k: v for k, v in host.items() if k.startswith("ansible_")}}
        for key, value in merged.items():
            if key in {"ansible_host", "ansible_user", "ansible_port"}:
                continue
            if isinstance(value, bool):
                parts.append(f"{key}={'False' if not value else 'True'}")
            else:
                parts.append(f"{key}={shlex.quote(str(value))}")
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def _ansible_env(deployment: InfrastructureDeployment) -> dict[str, str]:
    env: dict[str, str] = {}
    if is_gcp_docker_vm_apply_eligible(deployment):
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    return env


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
        "ansible_env": _ansible_env(deployment),
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
