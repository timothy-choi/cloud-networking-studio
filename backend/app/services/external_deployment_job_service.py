"""External deployment job orchestration (Step 57A/57B)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_masking import mask_secrets_in_text, scrub_sensitive_dict
from app.models.deployment_target import DeploymentTarget
from app.models.external_deployment_job import ExternalDeploymentJob
from app.models.topology import Topology
from app.models.user import User
from app.services.audit_service import record_audit
from app.services import remote_docker_executor_service as remote_docker_svc

JOB_MODES = frozenset({"validate", "plan", "apply", "destroy"})
REMOTE_DOCKER_JOB_MODES = frozenset({"validate", "plan", "apply", "destroy"})
STUB_TARGET_JOB_MODES = frozenset({"validate", "plan"})


def enabled_modes_for_target(target_type: str) -> frozenset[str]:
    if target_type == "remote_docker":
        return REMOTE_DOCKER_JOB_MODES
    return STUB_TARGET_JOB_MODES


def list_jobs_for_topology(db: Session, topology_id) -> list[ExternalDeploymentJob]:
    return list(
        db.scalars(
            select(ExternalDeploymentJob)
            .where(ExternalDeploymentJob.topology_id == topology_id)
            .order_by(ExternalDeploymentJob.created_at.desc())
        ).all()
    )


def get_job(db: Session, job_id) -> ExternalDeploymentJob | None:
    return db.get(ExternalDeploymentJob, job_id)


def create_and_run_job(
    db: Session,
    *,
    topology: Topology,
    target: DeploymentTarget,
    actor: User,
    mode: str,
) -> ExternalDeploymentJob:
    if mode not in JOB_MODES:
        raise ValueError(f"Invalid job mode: {mode}")
    allowed = enabled_modes_for_target(target.target_type)
    if mode not in allowed:
        raise ValueError(
            f"Mode '{mode}' is not enabled for target_type '{target.target_type}'. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    if mode in {"apply", "destroy"} and (target.config_json or {}).get("workload_apply_disabled"):
        reason = (target.config_json or {}).get("workload_apply_disabled_reason") or (
            "Workload apply is disabled for this target."
        )
        raise ValueError(reason)
    if target.project_id != topology.project_id:
        raise ValueError("Target does not belong to topology project")
    if target.status != "active":
        raise ValueError("Deployment target is not active")

    job = ExternalDeploymentJob(
        project_id=topology.project_id,
        topology_id=topology.id,
        target_id=target.id,
        mode=mode,
        status="queued",
        artifact_refs=[],
        created_by_user_id=actor.id,
    )
    db.add(job)
    db.flush()
    record_audit(
        db,
        action="external_deployment_job.created",
        resource_type="external_deployment_job",
        resource_id=job.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology.id),
                "target_id": str(target.id),
                "mode": mode,
                "target_type": target.target_type,
            }
        ),
    )
    _execute_job(db, job=job, topology=topology, target=target)
    record_audit(
        db,
        action=f"external_deployment_job.{job.mode}",
        resource_type="external_deployment_job",
        resource_id=job.id,
        project_id=topology.project_id,
        actor_user_id=actor.id,
        status=job.status,
        metadata=scrub_sensitive_dict(
            {
                "mode": job.mode,
                "status": job.status,
                "target_type": target.target_type,
            }
        ),
    )
    return job


def _execute_job(
    db: Session,
    *,
    job: ExternalDeploymentJob,
    topology: Topology,
    target: DeploymentTarget,
) -> None:
    job.status = "running"
    job.started_at = datetime.now(UTC)
    db.flush()

    try:
        if target.target_type == "remote_docker":
            logs, artifacts = _run_remote_docker(db, job=job, topology=topology, target=target)
            job.logs = logs
            job.artifact_refs = artifacts
            job.status = "succeeded"
        else:
            _execute_stub_job(job=job, topology=topology, target=target)
    except ValueError as exc:
        job.status = "failed"
        prefix = job.logs or ""
        err_line = f"[external-job] ERROR: {exc}"
        job.logs = mask_secrets_in_text(
            f"{prefix}\n{err_line}".strip() if prefix else err_line
        )
    except Exception as exc:  # noqa: BLE001 — surface as failed job, not HTTP 500
        job.status = "failed"
        prefix = job.logs or ""
        err_line = f"[external-job] ERROR: {type(exc).__name__}: {exc}"
        job.logs = mask_secrets_in_text(
            f"{prefix}\n{err_line}".strip() if prefix else err_line
        )

    job.finished_at = datetime.now(UTC)
    db.flush()


def _run_remote_docker(
    db: Session,
    *,
    job: ExternalDeploymentJob,
    topology: Topology,
    target: DeploymentTarget,
) -> tuple[str, list]:
    if job.mode == "validate":
        return remote_docker_svc.execute_validate(db, job=job, target=target, topology=topology)
    if job.mode == "plan":
        return remote_docker_svc.execute_plan(db, job=job, target=target, topology=topology)
    if job.mode == "apply":
        return remote_docker_svc.execute_apply(db, job=job, target=target, topology=topology)
    if job.mode == "destroy":
        return remote_docker_svc.execute_destroy(db, job=job, target=target, topology=topology)
    raise ValueError(f"Unsupported mode: {job.mode}")


def _execute_stub_job(
    *,
    job: ExternalDeploymentJob,
    topology: Topology,
    target: DeploymentTarget,
) -> None:
    lines: list[str] = [
        f"[external-job] id={job.id}",
        f"[external-job] topology={topology.name} ({topology.id})",
        f"[external-job] target={target.name} ({target.target_type})",
        f"[external-job] mode={job.mode}",
    ]
    if job.mode == "validate":
        lines.append("[external-job] Validating target configuration (stub)...")
        job.status = "succeeded"
    elif job.mode == "plan":
        plan_ref = {
            "type": "plan_summary",
            "uri": f"stub://external-jobs/{job.id}/plan.json",
            "target_type": target.target_type,
        }
        job.artifact_refs = [plan_ref]
        lines.append(f"[external-job] Plan artifact: {plan_ref['uri']}")
        job.status = "succeeded"
    else:
        lines.append(f"[external-job] ERROR: mode '{job.mode}' not supported for {target.target_type}")
        job.status = "failed"
    job.logs = mask_secrets_in_text("\n".join(lines)) or ""
