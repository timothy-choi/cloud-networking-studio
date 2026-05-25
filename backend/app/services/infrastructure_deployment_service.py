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
from app.services.infra_security import sanitize_variables, validate_provider
from app.services.infra_template_registry import validate_template_provider


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


def create_deployment(
    db: Session,
    *,
    topology: Topology,
    actor: User,
    name: str,
    template_id: str,
    provider: str,
    variables: dict | None,
) -> InfrastructureDeployment:
    validate_provider(provider, SUPPORTED_PROVIDERS)
    validate_template_provider(template_id, provider)
    clean_vars = sanitize_variables(variables)
    deployment = InfrastructureDeployment(
        project_id=topology.project_id,
        topology_id=topology.id,
        name=name.strip(),
        template_id=template_id,
        provider=provider,
        status="pending",
        variables_json=clean_vars,
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
    hosts = deployment.outputs_json.get("hosts") or []
    created: list[dict] = []
    for host in hosts:
        if not isinstance(host, dict):
            continue
        host_name = str(host.get("name") or "runtime-host")
        public_ip = host.get("public_ip") or host.get("private_ip")
        if not public_ip:
            continue
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
                "remote_workdir": "/opt/cns-external-deployments",
                "supports_compose": True,
            },
            credentials_ref="env:CNS_REMOTE_DOCKER_SSH_KEY_PATH",
            status="active",
        )
        created.append(
            {
                "target_id": str(target.id),
                "name": target.name,
                "host": public_ip,
                "target_type": "remote_docker",
            }
        )
    deployment.runtime_targets_json = created
    db.flush()
    return created


def run_validate(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    try:
        deployment.status = "validating"
        deployment.events_json = append_event(deployment.events_json, "validate_started")
        db.flush()

        tf_validate = _new_execution(db, deployment=deployment, execution_type="terraform", mode="validate")
        tf_svc.execute_validate(db, execution=tf_validate, deployment=deployment)

        tf_fmt = _new_execution(db, deployment=deployment, execution_type="terraform", mode="fmt")
        tf_svc.execute_fmt(db, execution=tf_fmt, deployment=deployment)

        deployment.status = "pending"
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
        deployment.status = "planning"
        deployment.events_json = append_event(deployment.events_json, "plan_started")
        db.flush()

        tf_plan = _new_execution(db, deployment=deployment, execution_type="terraform", mode="plan")
        _, artifacts, outputs = tf_svc.execute_plan(db, execution=tf_plan, deployment=deployment)
        deployment.outputs_json = {**(deployment.outputs_json or {}), **outputs}
        plan_summary = next((a for a in artifacts if a.get("type") == "plan_summary"), None)
        deployment.plan_summary_json = plan_summary
        deployment.state_metadata_json = {
            **(deployment.state_metadata_json or {}),
            "backend": "local",
            "workspace": f"cns-infra-{str(deployment.id)[:8]}",
        }

        deployment.status = "awaiting_confirmation"
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
    deployment.metrics_json = record_metric(
        deployment.metrics_json,
        "terraform_apply_duration_ms",
        int((time.monotonic() - started) * 1000),
    )

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
    deployment.events_json = append_event(
        deployment.events_json,
        "runtime_ready",
        message=f"Registered {len(targets)} remote_docker target(s)",
        metadata={"targets": targets, "mock": True},
    )
    deployment.metrics_json = record_metric(
        deployment.metrics_json,
        "ansible_duration_ms",
        int((time.monotonic() - ansible_started) * 1000),
    )
    deployment.metrics_json = increment_counter(deployment.metrics_json, "success_count")
    deployment.error_message = None


def confirm_and_apply(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    if deployment.status != "awaiting_confirmation":
        raise ValueError(f"Deployment must be awaiting_confirmation (current: {deployment.status})")

    started = time.monotonic()
    deployment.confirmed_at = datetime.now(UTC)
    deployment.confirmed_by_user_id = actor.id
    deployment.status = "applying"
    deployment.events_json = append_event(deployment.events_json, "apply_started")
    db.flush()

    try:
        if is_mock_infrastructure_deployment(deployment):
            _confirm_and_apply_mock(db, deployment=deployment, actor=actor, started=started)
        else:
            tf_apply = _new_execution(db, deployment=deployment, execution_type="terraform", mode="apply")
            _, _, outputs = tf_svc.execute_apply(db, execution=tf_apply, deployment=deployment)
            deployment.outputs_json = {**(deployment.outputs_json or {}), **outputs}
            deployment.events_json = append_event(deployment.events_json, "apply_completed")
            deployment.metrics_json = record_metric(
                deployment.metrics_json,
                "terraform_apply_duration_ms",
                int((time.monotonic() - started) * 1000),
            )

            inv_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="inventory")
            _, _, inv_outputs = ansible_svc.execute_inventory(db, execution=inv_exec, deployment=deployment)
            deployment.inventory_json = inv_outputs.get("inventory") or ansible_svc.generate_inventory(deployment)

            deployment.status = "configuring"
            deployment.events_json = append_event(
                deployment.events_json,
                "configure_started",
                message="Ansible configuration started",
            )
            db.flush()

            ansible_started = time.monotonic()
            ansible_exec = _new_execution(db, deployment=deployment, execution_type="ansible", mode="playbook")
            ansible_svc.execute_configure(db, execution=ansible_exec, deployment=deployment)
            deployment.events_json = append_event(
                deployment.events_json,
                "configure_completed",
                message="Host configuration completed",
            )

            targets = _register_runtime_targets(db, deployment=deployment, actor=actor)
            deployment.status = "succeeded"
            deployment.events_json = append_event(
                deployment.events_json,
                "runtime_ready",
                message=f"Registered {len(targets)} remote_docker target(s)",
                metadata={"targets": targets},
            )
            deployment.metrics_json = record_metric(
                deployment.metrics_json,
                "ansible_duration_ms",
                int((time.monotonic() - ansible_started) * 1000),
            )
            deployment.metrics_json = increment_counter(deployment.metrics_json, "success_count")
            deployment.error_message = None
    except ValueError as exc:
        deployment.status = "failed"
        deployment.error_message = str(exc)
        deployment.events_json = append_event(deployment.events_json, "failed", message=str(exc))
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


def destroy_deployment(db: Session, *, deployment: InfrastructureDeployment, actor: User) -> InfrastructureDeployment:
    if deployment.status in {"destroyed", "destroying"}:
        return deployment

    deployment.status = "destroying"
    deployment.events_json = append_event(deployment.events_json, "destroy_started")
    db.flush()

    try:
        tf_destroy = _new_execution(db, deployment=deployment, execution_type="terraform", mode="destroy")
        tf_svc.execute_destroy(db, execution=tf_destroy, deployment=deployment)
        deployment.status = "destroyed"
        deployment.destroyed_at = datetime.now(UTC)
        deployment.runtime_targets_json = []
        deployment.events_json = append_event(deployment.events_json, "destroyed")
        deployment.metrics_json = increment_counter(deployment.metrics_json, "destroy_count")
        deployment.error_message = None
    except ValueError as exc:
        deployment.status = "failed"
        deployment.error_message = str(exc)
        deployment.events_json = append_event(deployment.events_json, "failed", message=str(exc))
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
