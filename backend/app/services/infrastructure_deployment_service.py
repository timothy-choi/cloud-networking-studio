"""Infrastructure deployment orchestration (Step 57C)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_masking import scrub_sensitive_dict
from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.infrastructure_execution import InfrastructureExecution
from app.models.topology import Topology
from app.models.user import User
from app.schemas.infrastructure_deployment import SUPPORTED_PROVIDERS
from app.services import ansible_executor_service as ansible_svc
from app.services import deployment_target_service as target_svc
from app.services import terraform_executor_service as tf_svc
from app.services.audit_service import record_audit
from app.services.infra_observability import append_event, increment_counter, record_metric
from app.services.infra_security import (
    is_real_cloud_provider,
    sanitize_variables,
    validate_provider,
    validate_template_variables,
)
from app.services.infra_template_registry import validate_template_provider
from app.services.infra_apply_safety import (
    InfraApplySafetyError,
    InfraInvalidStateError,
    build_apply_safety_checklist,
    is_gcp_docker_vm_apply_eligible,
    validate_gcp_apply_safety,
    variables_hash,
)
from app.services import infra_ssh_readiness as ssh_readiness_svc
from app.services import infra_deployment_phases as infra_phases
from app.services.remote_ssh_public_key_service import resolve_remote_docker_ssh_public_key
from app.runtime.infra_runner_client import InfraRunnerClientError


from app.services.terraform_credentials_service import resolve_terraform_credentials_env


class RealCloudApplyDisabledError(Exception):
    """Raised when confirm/apply is attempted for unsupported real cloud providers."""

    def __init__(self, message: str = "Real cloud apply is disabled for this provider.") -> None:
        super().__init__(message)
        self.message = message


class PlanOnlyDestroyDisabledError(Exception):
    """Raised when destroy is attempted without a prior apply."""

    def __init__(self, message: str = "Nothing to destroy: plan-only deployment.") -> None:
        super().__init__(message)
        self.message = message


def list_deployments_for_topology(db: Session, topology_id: UUID) -> list[InfrastructureDeployment]:
    return list(
        db.scalars(
            select(InfrastructureDeployment)
            .where(InfrastructureDeployment.topology_id == topology_id)
            .order_by(InfrastructureDeployment.created_at.desc())
        ).all()
    )


def get_deployment(db: Session, deployment_id: UUID) -> InfrastructureDeployment | None:
    return db.get(InfrastructureDeployment, deployment_id)


def list_executions(db: Session, deployment_id: UUID) -> list[InfrastructureExecution]:
    return list(
        db.scalars(
            select(InfrastructureExecution)
            .where(InfrastructureExecution.infrastructure_deployment_id == deployment_id)
            .order_by(InfrastructureExecution.created_at.asc())
        ).all()
    )


def _assert_cloud_template_ready(template_id: str, provider: str) -> None:
    if template_id == "docker-vm" and provider == "aws":
        raise ValueError("AWS docker-vm Terraform support is coming soon.")


def _require_real_cloud_ready(deployment: InfrastructureDeployment) -> None:
    _assert_cloud_template_ready(deployment.template_id, deployment.provider)
    if not is_real_cloud_provider(deployment.provider):
        return
    ref = (deployment.credentials_ref or "").strip()
    if not ref:
        raise ValueError("Terraform credentials_ref is not configured on the server.")
    resolve_terraform_credentials_env(deployment.provider, ref)
    if is_gcp_docker_vm_apply_eligible(deployment):
        resolve_remote_docker_ssh_public_key()


POST_APPLY_DESTROYABLE_STATUSES = infra_phases.DESTROYABLE_STATUSES

RETRY_CONFIGURATION_STATUSES = infra_phases.RETRY_CONFIGURATION_STATUSES


def _has_been_applied(deployment: InfrastructureDeployment) -> bool:
    return infra_phases.has_terraform_apply_completed(deployment)


def _can_retry_configuration(deployment: InfrastructureDeployment) -> bool:
    return infra_phases.can_retry_configuration(deployment)


def _mark_terraform_apply_started(db: Session, *, deployment: InfrastructureDeployment) -> None:
    infra_phases.persist_workspace_metadata(deployment)
    infra_phases.mark_phases(
        deployment,
        db=db,
        flush=True,
        **{infra_phases.PHASE_TERRAFORM_APPLY_STARTED: True},
    )


def _persist_terraform_apply_completion(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    apply_execution_id: UUID,
    outputs: dict,
    started: float,
) -> None:
    """Persist Terraform outputs and apply marker before host configuration begins."""
    deployment.outputs_json = {**(deployment.outputs_json or {}), **outputs}
    deployment.state_metadata_json = {
        **(deployment.state_metadata_json or {}),
        **infra_phases.workspace_metadata(deployment),
        "applied_at": datetime.now(UTC).isoformat(),
        "apply_execution_id": str(apply_execution_id),
        "terraform_apply_completed": True,
        "terraform_apply_started": True,
    }
    deployment.status = "configuring"
    infra_phases.mark_phases(
        deployment,
        **{
            infra_phases.PHASE_TERRAFORM_APPLY_STARTED: True,
            infra_phases.PHASE_TERRAFORM_APPLY_COMPLETED: True,
            infra_phases.PHASE_TERRAFORM_OUTPUTS_CAPTURED: True,
        },
    )
    deployment.events_json = append_event(deployment.events_json, "apply_completed")
    deployment.metrics_json = record_metric(
        deployment.metrics_json,
        "terraform_apply_duration_ms",
        int((time.monotonic() - started) * 1000),
    )
    db.flush()


def _can_destroy_deployment(deployment: InfrastructureDeployment) -> bool:
    return infra_phases.can_destroy_deployment(
        deployment,
        is_mock=is_mock_infrastructure_deployment(deployment),
    )


def _append_configuration_progress(
    deployment: InfrastructureDeployment,
    *,
    message: str,
    metadata: dict | None = None,
) -> None:
    deployment.events_json = append_event(
        deployment.events_json,
        "configuration_progress",
        message=message,
        metadata=metadata or {},
    )


def _run_host_configuration(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
) -> tuple[str, str | None]:
    """Run SSH readiness, Ansible inventory/configure, and Docker verification."""
    try:
        _append_configuration_progress(deployment, message="Generating Ansible inventory")
        inv_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="inventory")
        _, _, inv_outputs = ansible_svc.execute_inventory(db, execution=inv_exec, deployment=deployment)
        deployment.inventory_json = inv_outputs.get("inventory") or ansible_svc.generate_inventory(deployment)

        if is_gcp_docker_vm_apply_eligible(deployment):
            infra_phases.mark_phases(
                deployment,
                db=db,
                flush=True,
                **{infra_phases.PHASE_SSH_READINESS_STARTED: True},
            )
            _append_configuration_progress(deployment, message="SSH readiness: waiting for port 22 and authentication")
            readiness_exec = _new_execution(
                db, deployment=deployment, execution_type="ansible", mode="ssh_readiness"
            )
            readiness_exec.status = "running"
            readiness_exec.started_at = datetime.now(UTC)
            db.flush()
            try:
                readiness_log = ssh_readiness_svc.wait_for_ssh_ready(deployment)
                readiness_exec.status = "succeeded"
                readiness_exec.logs = readiness_log
                readiness_exec.finished_at = datetime.now(UTC)
                infra_phases.mark_phases(
                    deployment,
                    db=db,
                    flush=True,
                    **{infra_phases.PHASE_SSH_READINESS_COMPLETED: True},
                )
                deployment.events_json = append_event(
                    deployment.events_json,
                    "ssh_readiness_completed",
                    message="SSH port and authentication ready",
                    metadata={"log_preview": readiness_log[-2000:]},
                )
            except ValueError as exc:
                readiness_exec.status = "failed"
                readiness_exec.logs = str(exc)
                readiness_exec.finished_at = datetime.now(UTC)
                deployment.events_json = append_event(
                    deployment.events_json,
                    "ssh_readiness_failed",
                    message=str(exc),
                )
                db.flush()
                raise

        deployment.status = "configuring"
        infra_phases.mark_phases(
            deployment,
            db=db,
            flush=True,
            **{infra_phases.PHASE_CONFIGURATION_STARTED: True},
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "configure_started",
            message="Ansible configuration started",
        )
        _append_configuration_progress(deployment, message="Host configuration: running Ansible playbooks")
        db.flush()

        ansible_started = time.monotonic()
        ansible_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="playbook")
        ansible_svc.execute_configure(db, execution=ansible_exec, deployment=deployment)

        if is_gcp_docker_vm_apply_eligible(deployment):
            _append_configuration_progress(deployment, message="Host configuration: verifying Docker and Compose")
            verify_exec = _new_execution(
                db, deployment=deployment, execution_type="ansible", mode="docker_verify"
            )
            verify_exec.status = "running"
            verify_exec.started_at = datetime.now(UTC)
            db.flush()
            verify_log = ssh_readiness_svc.verify_remote_docker(deployment)
            verify_exec.status = "succeeded"
            verify_exec.logs = verify_log
            verify_exec.finished_at = datetime.now(UTC)

            _append_configuration_progress(deployment, message="Host configuration: verifying remote workdir permissions")
            workdir_exec = _new_execution(
                db, deployment=deployment, execution_type="ansible", mode="workdir_verify"
            )
            workdir_exec.status = "running"
            workdir_exec.started_at = datetime.now(UTC)
            db.flush()
            workdir_log = ssh_readiness_svc.verify_remote_workdir(deployment)
            workdir_exec.status = "succeeded"
            workdir_exec.logs = workdir_log
            workdir_exec.finished_at = datetime.now(UTC)

        infra_phases.mark_phases(
            deployment,
            db=db,
            flush=True,
            **{infra_phases.PHASE_CONFIGURATION_COMPLETED: True},
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "configure_completed",
            message="Host configuration completed",
        )
        deployment.metrics_json = record_metric(
            deployment.metrics_json,
            "ansible_duration_ms",
            int((time.monotonic() - ansible_started) * 1000),
        )
        return "completed", None
    except InfraRunnerClientError as exc:
        message = f"Configuration runner unavailable or timed out: {exc.message}"
        deployment.events_json = append_event(
            deployment.events_json,
            "configure_failed",
            message=message,
        )
        return "timeout", message
    except ValueError as exc:
        deployment.events_json = append_event(
            deployment.events_json,
            "configure_failed",
            message=str(exc),
        )
        return "failed", str(exc)


def _registration_failure_reason(deployment: InfrastructureDeployment) -> str:
    for ev in reversed(deployment.events_json or []):
        ev_type = ev.get("type")
        if ev_type in {"runtime_target_creation_skipped", "runtime_target_creation_failed"}:
            return str(ev.get("message") or "Runtime target registration failed.")
    return "Runtime target registration failed."


def _finalize_after_configuration(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    configuration_status: str,
    configuration_error: str | None,
) -> None:
    if configuration_status != "completed":
        timed_out = configuration_status == "timeout"
        deployment.status = infra_phases.configuration_failure_status(timed_out=timed_out)
        deployment.error_message = configuration_error or "Host configuration failed."
        if _has_been_applied(deployment):
            deployment.events_json = append_event(
                deployment.events_json,
                "recovery_hint",
                message=infra_phases.RECOVERY_MESSAGE,
            )
        db.flush()
        return

    targets = _register_runtime_targets(db, deployment=deployment, actor=actor)
    if targets:
        infra_phases.mark_phases(
            deployment,
            db=db,
            flush=False,
            **{infra_phases.PHASE_RUNTIME_TARGET_REGISTERED: True},
        )
    if not targets and not is_mock_infrastructure_deployment(deployment):
        reason = _registration_failure_reason(deployment)
        deployment.status = "registration_failed"
        deployment.error_message = reason
        deployment.events_json = append_event(
            deployment.events_json,
            "registration_failed",
            message=reason,
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "recovery_hint",
            message="Retry configuration to re-register runtime target, or destroy infrastructure.",
        )
        db.flush()
        return

    deployment.status = "succeeded"
    deployment.error_message = None
    deployment.events_json = append_event(
        deployment.events_json,
        "runtime_ready",
        message=f"Registered {len(targets)} remote_docker target(s)",
        metadata={"targets": targets, "configuration_status": configuration_status},
    )
    deployment.metrics_json = increment_counter(deployment.metrics_json, "success_count")
    db.flush()


def retry_configuration(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
) -> InfrastructureDeployment:
    """Retry host configuration only (SSH wait, Ansible, Docker verify). Does not re-run Terraform."""
    if not _can_retry_configuration(deployment):
        raise InfraInvalidStateError(
            "Retry configuration requires a completed Terraform apply and incomplete host configuration "
            f"(current: {deployment.status})"
        )

    _require_real_cloud_ready(deployment)
    deployment.events_json = append_event(
        deployment.events_json,
        "configure_retry_started",
        message="Retrying host configuration",
    )
    db.flush()

    try:
        configuration_status, configuration_error = _run_host_configuration(db, deployment=deployment)
        _finalize_after_configuration(
            db,
            deployment=deployment,
            actor=actor,
            configuration_status=configuration_status,
            configuration_error=configuration_error,
        )
    except ValueError as exc:
        deployment.status = "configuration_failed"
        deployment.error_message = str(exc)
        deployment.events_json = append_event(deployment.events_json, "configure_failed", message=str(exc))
        if _has_been_applied(deployment):
            deployment.events_json = append_event(
                deployment.events_json,
                "recovery_hint",
                message=infra_phases.RECOVERY_MESSAGE,
            )

    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.retry_configure",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment


def create_deployment(
    db: Session,
    *,
    topology: Topology,
    actor: User,
    name: str,
    template_id: str,
    provider: str,
    variables: dict | None,
    credentials_ref: str | None = None,
) -> InfrastructureDeployment:
    validate_provider(provider, SUPPORTED_PROVIDERS)
    validate_template_provider(template_id, provider)
    clean_vars = sanitize_variables(variables)
    validate_template_variables(template_id, provider, clean_vars)
    _assert_cloud_template_ready(template_id, provider)
    cred_ref = (credentials_ref or "").strip() or None
    if is_real_cloud_provider(provider):
        if not cred_ref:
            raise ValueError("Terraform credentials_ref is not configured on the server.")
        resolve_terraform_credentials_env(provider, cred_ref)

    deployment = InfrastructureDeployment(
        project_id=topology.project_id,
        topology_id=topology.id,
        name=name.strip(),
        template_id=template_id,
        provider=provider,
        status="pending",
        variables_json=clean_vars,
        credentials_ref=cred_ref,
        created_by_user_id=actor.id,
        events_json=append_event([], "created", message="Infrastructure deployment created"),
    )
    db.add(deployment)
    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.created",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology.id),
                "template_id": template_id,
                "provider": provider,
            }
        ),
    )
    return deployment


def _new_execution(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    execution_type: str,
    mode: str,
) -> InfrastructureExecution:
    execution = InfrastructureExecution(
        infrastructure_deployment_id=deployment.id,
        execution_type=execution_type,
        mode=mode,
        status="queued",
    )
    db.add(execution)
    db.flush()
    return execution


def _register_runtime_targets(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
) -> list[dict]:
    """Register runtime targets after infra apply/configure. Idempotent per infra deployment."""
    existing = target_svc.list_targets_for_infrastructure_deployment(db, deployment.id)
    if existing:
        snapshots = [target_svc.runtime_target_snapshot(t) for t in existing]
        deployment.runtime_targets_json = snapshots
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_target_creation_skipped",
            message="Runtime target already registered for this infrastructure deployment",
            metadata={"targets": snapshots, "reused": True},
        )
        db.flush()
        return snapshots

    is_mock = is_mock_infrastructure_deployment(deployment)
    if is_mock:
        hosts = deployment.outputs_json.get("hosts") if deployment.outputs_json else None
        if not hosts:
            hosts = [
                {
                    "name": f"{deployment.name}-vm-1",
                    "public_ip": "203.0.113.10",
                    "private_ip": "10.0.0.10",
                    "ssh_user": "ubuntu",
                    "ssh_port": 22,
                }
            ]
    else:
        hosts = ssh_readiness_svc.resolve_inventory_hosts(deployment)
    if not isinstance(hosts, list) or not hosts:
        reason = "No host outputs available to register a runtime target"
        deployment.runtime_targets_json = []
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_target_creation_skipped",
            message=reason,
            metadata={"template_id": deployment.template_id, "provider": deployment.provider},
        )
        db.flush()
        return []

    if is_mock:
        hosts = hosts[:1]

    created: list[dict] = []
    errors: list[str] = []
    for host in hosts:
        if not isinstance(host, dict):
            continue
        host_name = str(host.get("name") or "runtime-host")
        public_ip = host.get("public_ip") or host.get("private_ip")
        if not public_ip:
            errors.append(f"Host '{host_name}' missing public/private IP")
            continue
        public_ip = str(public_ip)
        mock_overrides = target_svc.mock_target_config_overrides(is_mock=is_mock, host=public_ip)
        real_overrides: dict = {}
        if is_gcp_docker_vm_apply_eligible(deployment) and not is_mock:
            real_overrides = {
                "target_source": "terraform_gcp_docker_vm",
                "infrastructure_source": "terraform_gcp_docker_vm",
            }
        try:
            target = target_svc.create_target(
                db,
                project_id=deployment.project_id,
                actor=actor,
                name=f"{deployment.name}-{host_name}"[:128],
                target_type="remote_docker",
                config_json={
                    "host": public_ip,
                    "ssh_user": host.get("ssh_user") or "ubuntu",
                    "ssh_port": host.get("ssh_port") or 22,
                    "remote_workdir": ssh_readiness_svc.REMOTE_DOCKER_EXTERNAL_WORKDIR,
                    "supports_compose": True,
                    **mock_overrides,
                    **real_overrides,
                },
                credentials_ref="env:CNS_REMOTE_DOCKER_SSH_KEY_PATH",
                status="active",
                infrastructure_deployment_id=deployment.id,
            )
            snapshot = target_svc.runtime_target_snapshot(target)
            created.append(snapshot)
            deployment.events_json = append_event(
                deployment.events_json,
                "runtime_target_created",
                message=f"Registered runtime target {target.name}",
                metadata={"target": snapshot},
            )
        except ValueError as exc:
            errors.append(str(exc))
            deployment.events_json = append_event(
                deployment.events_json,
                "runtime_target_creation_failed",
                message=str(exc),
                metadata={"host": public_ip, "host_name": host_name},
            )

    deployment.runtime_targets_json = created
    if not created and errors:
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_target_creation_skipped",
            message=f"No runtime target created: {'; '.join(errors)}",
            metadata={"errors": errors},
        )
    db.flush()
    return created


def run_validate(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    try:
        _require_real_cloud_ready(deployment)
        deployment.status = "validating"
        deployment.events_json = append_event(deployment.events_json, "validate_started")
        db.flush()

        tf_validate = _new_execution(db, deployment=deployment, execution_type="terraform", mode="validate")
        tf_svc.execute_validate(db, execution=tf_validate, deployment=deployment)

        tf_fmt = _new_execution(db, deployment=deployment, execution_type="terraform", mode="fmt")
        tf_svc.execute_fmt(db, execution=tf_fmt, deployment=deployment)

        deployment.status = "validated"
        deployment.events_json = append_event(
            deployment.events_json,
            "validate_completed",
            message="Terraform validate/fmt succeeded",
        )
        deployment.error_message = None
    except ValueError as exc:
        deployment.status = "failed"
        deployment.error_message = str(exc)
        deployment.events_json = append_event(deployment.events_json, "failed", message=str(exc))
        deployment.metrics_json = increment_counter(deployment.metrics_json, "failure_count")
    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.validate",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment


def run_plan(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    started = time.monotonic()
    try:
        if deployment.status not in {"validated", "failed"}:
            raise ValueError("Run Validate first (deployment must be in validated status).")
        _require_real_cloud_ready(deployment)
        deployment.status = "planning"
        deployment.events_json = append_event(deployment.events_json, "plan_started")
        db.flush()

        tf_plan = _new_execution(db, deployment=deployment, execution_type="terraform", mode="plan")
        _, artifacts, outputs = tf_svc.execute_plan(db, execution=tf_plan, deployment=deployment)
        deployment.outputs_json = {**(deployment.outputs_json or {}), **outputs}
        plan_summary = next((a for a in artifacts if a.get("type") == "plan_summary"), None)
        var_hash = variables_hash(deployment.variables_json)
        deployment.state_metadata_json = {
            **(deployment.state_metadata_json or {}),
            "backend": "local",
            "workspace_id": str(deployment.id),
            "workspace": f"cns-infra-{str(deployment.id)[:8]}",
            "plan_execution_id": str(tf_plan.id),
            "plan_file": "tfplan",
            "variables_hash": var_hash,
        }
        deployment.status = "awaiting_confirmation"
        if plan_summary and is_gcp_docker_vm_apply_eligible(deployment):
            plan_summary = {
                **plan_summary,
                "safety_checklist": build_apply_safety_checklist(deployment),
            }
        deployment.plan_summary_json = plan_summary
        deployment.events_json = append_event(
            deployment.events_json,
            "plan_completed",
            message="Terraform plan completed — awaiting user confirmation",
            metadata={"plan_summary": plan_summary or {}},
        )
        deployment.metrics_json = record_metric(
            deployment.metrics_json,
            "plan_duration_ms",
            int((time.monotonic() - started) * 1000),
        )
        deployment.error_message = None
    except ValueError as exc:
        deployment.status = "failed"
        deployment.error_message = str(exc)
        deployment.events_json = append_event(deployment.events_json, "failed", message=str(exc))
        deployment.metrics_json = increment_counter(deployment.metrics_json, "failure_count")
    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.plan",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment


def run_validate_and_plan(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    deployment = run_validate(db, deployment=deployment, actor=actor)
    if deployment.status == "failed":
        return deployment
    return run_plan(db, deployment=deployment, actor=actor)


MOCK_INFRA_PROVIDERS = frozenset({"local", "mock"})


def is_mock_infrastructure_deployment(deployment: InfrastructureDeployment) -> bool:
    return deployment.provider in MOCK_INFRA_PROVIDERS or deployment.template_id == "local-mock"


def _complete_mock_execution(
    execution: InfrastructureExecution,
    *,
    logs: str,
    artifacts: list[dict] | None = None,
    duration_ms: int = 5,
) -> None:
    execution.status = "succeeded"
    execution.logs = logs
    execution.artifact_refs = artifacts or []
    execution.duration_ms = duration_ms
    execution.started_at = datetime.now(UTC)
    execution.finished_at = datetime.now(UTC)


def _confirm_and_apply_mock(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    started: float,
) -> None:
    """Simulate apply/configure for local/mock without runner SSH/Ansible."""
    tf_apply = _new_execution(db, deployment=deployment, execution_type="terraform", mode="apply")
    _complete_mock_execution(
        tf_apply,
        logs="[mock] terraform apply completed\n",
        artifacts=[{"type": "apply_summary", "uri": f"mock://infra/{deployment.id}/apply"}],
    )
    deployment.outputs_json = {
        **(deployment.outputs_json or {}),
        "vm_count": deployment.outputs_json.get("vm_count") or deployment.variables_json.get("vm_count") or 1,
        "region": deployment.outputs_json.get("region") or deployment.variables_json.get("region") or "local",
        "hosts": deployment.outputs_json.get("hosts")
        or [
            {
                "name": f"{deployment.name}-vm-1",
                "public_ip": "203.0.113.10",
                "private_ip": "10.0.0.10",
                "ssh_user": "ubuntu",
                "ssh_port": 22,
            }
        ],
    }
    deployment.events_json = append_event(deployment.events_json, "apply_completed")
    deployment.state_metadata_json = {
        **(deployment.state_metadata_json or {}),
        "applied_at": datetime.now(UTC).isoformat(),
        "apply_execution_id": str(tf_apply.id),
        "terraform_apply_completed": True,
    }
    deployment.metrics_json = record_metric(
        deployment.metrics_json,
        "terraform_apply_duration_ms",
        int((time.monotonic() - started) * 1000),
    )
    db.flush()

    inv_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="inventory")
    inventory = ansible_svc.generate_inventory(deployment)
    inv_logs = ansible_svc.inventory_ini_preview(inventory)
    _complete_mock_execution(
        inv_exec,
        logs=inv_logs,
        artifacts=[{"type": "inventory", "format": "ini", "preview": inv_logs[:4000]}],
    )
    deployment.inventory_json = inventory

    deployment.status = "configuring"
    deployment.events_json = append_event(
        deployment.events_json,
        "configure_started",
        message="Mock Ansible configuration started",
    )
    db.flush()

    ansible_started = time.monotonic()
    ansible_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="playbook")
    _complete_mock_execution(
        ansible_exec,
        logs="[mock] ansible-playbook configure completed (install-docker, install-docker-compose, cns-runtime-dirs)\n",
        artifacts=[{"type": "configure_summary", "uri": f"mock://infra/{deployment.id}/configure"}],
    )
    deployment.events_json = append_event(
        deployment.events_json,
        "configure_completed",
        message="Mock host configuration completed",
    )

    targets = _register_runtime_targets(db, deployment=deployment, actor=actor)
    deployment.status = "succeeded"
    if targets:
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_ready",
            message=f"Registered {len(targets)} remote_docker target(s)",
            metadata={"targets": targets, "mock": True},
        )
    else:
        skip = next(
            (ev for ev in reversed(deployment.events_json or []) if ev.get("type") == "runtime_target_creation_skipped"),
            None,
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_ready",
            message=skip.get("message") if skip else "Infrastructure succeeded without runtime targets",
            metadata={"targets": [], "mock": True},
        )
    deployment.metrics_json = record_metric(
        deployment.metrics_json,
        "ansible_duration_ms",
        int((time.monotonic() - ansible_started) * 1000),
    )
    deployment.metrics_json = increment_counter(deployment.metrics_json, "success_count")
    deployment.error_message = None


def confirm_and_apply(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    confirmation_text: str | None = None,
    unsafe_testing_override: bool = False,
) -> InfrastructureDeployment:
    can_apply, apply_block_reason = infra_phases.can_confirm_apply(deployment)
    if not can_apply:
        raise InfraInvalidStateError(apply_block_reason or infra_phases.APPLY_ALREADY_COMPLETED_MESSAGE)

    if is_real_cloud_provider(deployment.provider) and not is_mock_infrastructure_deployment(deployment):
        if not is_gcp_docker_vm_apply_eligible(deployment):
            raise RealCloudApplyDisabledError()
        if (confirmation_text or "").strip() != "APPLY":
            raise ValueError("Typed confirmation required: enter APPLY to confirm.")
        validate_gcp_apply_safety(deployment, unsafe_testing_override=unsafe_testing_override)
        _require_real_cloud_ready(deployment)

    started = time.monotonic()
    deployment.confirmed_at = datetime.now(UTC)
    deployment.confirmed_by_user_id = actor.id
    deployment.status = "applying"
    deployment.events_json = append_event(deployment.events_json, "apply_started")
    _mark_terraform_apply_started(db, deployment=deployment)

    try:
        if is_mock_infrastructure_deployment(deployment):
            _confirm_and_apply_mock(db, deployment=deployment, actor=actor, started=started)
        else:
            _confirm_and_apply_real(db, deployment=deployment, actor=actor, started=started)
    except InfraApplySafetyError:
        raise
    except InfraInvalidStateError:
        raise
    except InfraRunnerClientError as exc:
        if _has_been_applied(deployment):
            raise InfraInvalidStateError(infra_phases.STALE_PLAN_AFTER_APPLY_MESSAGE) from exc
        deployment.status = "apply_partial"
        deployment.error_message = f"Terraform apply request failed or timed out: {exc.message}"
        deployment.events_json = append_event(
            deployment.events_json,
            "apply_failed",
            message=deployment.error_message,
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "recovery_hint",
            message=infra_phases.RECOVERY_MESSAGE,
        )
        deployment.metrics_json = increment_counter(deployment.metrics_json, "failure_count")
    except ValueError as exc:
        if _has_been_applied(deployment):
            raise InfraInvalidStateError(infra_phases.STALE_PLAN_AFTER_APPLY_MESSAGE) from exc
        deployment.status = "failed"
        deployment.error_message = (
            infra_phases.STALE_PLAN_AFTER_APPLY_MESSAGE if "stale" in str(exc).lower() else str(exc)
        )
        deployment.events_json = append_event(
            deployment.events_json,
            "apply_failed",
            message=deployment.error_message,
        )
        deployment.events_json = append_event(deployment.events_json, "failed", message=deployment.error_message)
        deployment.metrics_json = increment_counter(deployment.metrics_json, "failure_count")

    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.apply",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment


def _confirm_and_apply_real(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    started: float,
) -> None:
    tf_apply = _new_execution(db, deployment=deployment, execution_type="terraform", mode="apply")
    try:
        _, _, outputs = tf_svc.execute_apply(db, execution=tf_apply, deployment=deployment)
    except (ValueError, InfraRunnerClientError) as exc:
        if _has_been_applied(deployment):
            raise InfraInvalidStateError(infra_phases.STALE_PLAN_AFTER_APPLY_MESSAGE) from exc
        raise
    _persist_terraform_apply_completion(
        db,
        deployment=deployment,
        apply_execution_id=tf_apply.id,
        outputs=outputs,
        started=started,
    )

    configuration_status, configuration_error = _run_host_configuration(db, deployment=deployment)
    _finalize_after_configuration(
        db,
        deployment=deployment,
        actor=actor,
        configuration_status=configuration_status,
        configuration_error=configuration_error,
    )


def destroy_deployment(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    confirmation_text: str | None = None,
) -> InfrastructureDeployment:
    if deployment.status in {"destroyed", "destroying"}:
        return deployment

    if not _can_destroy_deployment(deployment):
        raise PlanOnlyDestroyDisabledError()

    if is_gcp_docker_vm_apply_eligible(deployment):
        if (confirmation_text or "").strip() != "DESTROY":
            raise ValueError("Typed confirmation required: enter DESTROY to confirm destroy.")
        _require_real_cloud_ready(deployment)
        if infra_phases.has_terraform_resources(deployment) and not infra_phases.has_terraform_workspace(deployment):
            raise ValueError(
                "Terraform workspace/state is missing. Use force metadata cleanup if cloud resources cannot be reached."
            )
    elif is_real_cloud_provider(deployment.provider):
        raise PlanOnlyDestroyDisabledError()

    deployment.status = "destroying"
    infra_phases.mark_phases(
        deployment,
        db=db,
        flush=True,
        **{infra_phases.PHASE_DESTROY_STARTED: True},
    )
    deployment.events_json = append_event(deployment.events_json, "destroy_started")

    try:
        _deactivate_linked_runtime_targets(db, deployment=deployment, actor=actor)
        if is_gcp_docker_vm_apply_eligible(deployment):
            tf_destroy = _new_execution(db, deployment=deployment, execution_type="terraform", mode="destroy")
            tf_svc.execute_destroy(db, execution=tf_destroy, deployment=deployment)
        elif not is_mock_infrastructure_deployment(deployment):
            tf_destroy = _new_execution(db, deployment=deployment, execution_type="terraform", mode="destroy")
            tf_svc.execute_destroy(db, execution=tf_destroy, deployment=deployment)
        deployment.status = "destroyed"
        deployment.destroyed_at = datetime.now(UTC)
        deployment.runtime_targets_json = []
        infra_phases.mark_phases(
            deployment,
            db=db,
            flush=False,
            **{infra_phases.PHASE_DESTROY_COMPLETED: True},
        )
        deployment.events_json = append_event(deployment.events_json, "destroyed")
        deployment.metrics_json = increment_counter(deployment.metrics_json, "destroy_count")
        deployment.error_message = None
    except (ValueError, InfraRunnerClientError) as exc:
        if deployment.status == "destroying" and "nothing to destroy" in str(exc).lower():
            deployment.status = "destroyed"
            deployment.destroyed_at = datetime.now(UTC)
            infra_phases.mark_phases(
                deployment,
                db=db,
                flush=False,
                **{infra_phases.PHASE_DESTROY_COMPLETED: True},
            )
            deployment.events_json = append_event(
                deployment.events_json,
                "destroyed",
                message="Destroy completed (already absent)",
            )
            deployment.error_message = None
        else:
            deployment.status = "destroy_failed"
            deployment.error_message = str(getattr(exc, "message", exc))
            deployment.events_json = append_event(deployment.events_json, "destroy_failed", message=deployment.error_message)
            deployment.metrics_json = increment_counter(deployment.metrics_json, "failure_count")

    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.destroy",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment


def _deactivate_linked_runtime_targets(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
) -> None:
    _ = actor
    for target in target_svc.list_targets_for_infrastructure_deployment(db, deployment.id):
        target.status = "disabled"
        deployment.events_json = append_event(
            deployment.events_json,
            "runtime_target_deactivated",
            message=f"Deactivated runtime target {target.name} before destroy",
            metadata={"target_id": str(target.id)},
        )
    db.flush()


def get_apply_safety_preview(deployment: InfrastructureDeployment) -> dict:
    if not is_gcp_docker_vm_apply_eligible(deployment):
        return {"passed": False, "items": [], "apply_eligible": False}
    return {**build_apply_safety_checklist(deployment), "apply_eligible": True}


def force_metadata_cleanup(
    db: Session,
    *,
    deployment: InfrastructureDeployment,
    actor: User,
    confirmation_text: str | None = None,
) -> InfrastructureDeployment:
    """Mark deployment destroyed in metadata only when Terraform workspace/state is unavailable."""
    if deployment.status in {"destroyed", "destroying"}:
        return deployment
    if (confirmation_text or "").strip() != "CLEANUP":
        raise ValueError("Typed confirmation required: enter CLEANUP to confirm metadata-only cleanup.")
    if infra_phases.has_terraform_workspace(deployment):
        raise ValueError(
            "Terraform workspace/state still exists. Use Destroy infrastructure instead of metadata-only cleanup."
        )
    if not infra_phases.has_terraform_resources(deployment):
        raise ValueError("Nothing to cleanup: Terraform apply has not started for this deployment.")

    _deactivate_linked_runtime_targets(db, deployment=deployment, actor=actor)
    deployment.status = "destroyed"
    deployment.destroyed_at = datetime.now(UTC)
    deployment.runtime_targets_json = []
    deployment.error_message = None
    deployment.events_json = append_event(
        deployment.events_json,
        "metadata_cleanup_completed",
        message="Metadata-only cleanup completed. Cloud resources may still exist.",
    )
    infra_phases.mark_phases(
        deployment,
        db=db,
        flush=False,
        **{infra_phases.PHASE_DESTROY_COMPLETED: True},
    )
    db.flush()
    record_audit(
        db,
        action="infrastructure_deployment.force_metadata_cleanup",
        resource_type="infrastructure_deployment",
        resource_id=deployment.id,
        project_id=deployment.project_id,
        actor_user_id=actor.id,
        status=deployment.status,
    )
    return deployment
