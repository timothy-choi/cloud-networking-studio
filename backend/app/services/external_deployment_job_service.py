"""External deployment job orchestration (Step 57A — validate/plan stub only)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_masking import mask_secrets_in_text, scrub_sensitive_dict
from app.models.deployment_target import DeploymentTarget
from app.models.external_deployment_job import ExternalDeploymentJob
from app.models.topology import Topology
from app.models.user import User
from app.services.audit_service import record_audit

JOB_MODES = frozenset({"validate", "plan", "apply", "destroy"})
ENABLED_JOB_MODES = frozenset({"validate", "plan"})


def list_jobs_for_topology(db: Session, topology_id: UUID) -> list[ExternalDeploymentJob]:
    return list(
        db.scalars(
            select(ExternalDeploymentJob)
            .where(ExternalDeploymentJob.topology_id == topology_id)
            .order_by(ExternalDeploymentJob.created_at.desc())
        ).all()
    )


def get_job(db: Session, job_id: UUID) -> ExternalDeploymentJob | None:
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
            }
        ),
    )
    _execute_job_stub(db, job=job, topology=topology, target=target)
    record_audit(
        db,
        action="external_deployment_job.finished",
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


def _execute_job_stub(
    db: Session,
    *,
    job: ExternalDeploymentJob,
    topology: Topology,
    target: DeploymentTarget,
) -> None:
    now = datetime.now(UTC)
    job.status = "running"
    job.started_at = now
    lines: list[str] = [
        f"[external-job] id={job.id}",
        f"[external-job] topology={topology.name} ({topology.id})",
        f"[external-job] target={target.name} ({target.target_type})",
        f"[external-job] mode={job.mode}",
    ]

    if job.mode not in ENABLED_JOB_MODES:
        lines.append(
            f"[external-job] ERROR: mode '{job.mode}' is not enabled yet (Step 57A supports validate/plan only)."
        )
        lines.append("[external-job] Apply and destroy will be added in a later step.")
        job.status = "failed"
        job.logs = _join_logs(lines)
        job.finished_at = datetime.now(UTC)
        db.flush()
        return

    if job.mode == "validate":
        lines.append("[external-job] Validating target configuration (stub — no remote shell)...")
        if not target.config_json:
            lines.append("[external-job] WARN: config_json is empty")
        if target.credentials_ref:
            lines.append(
                f"[external-job] credentials_ref={target.credentials_ref} (secret values are not stored in DB)"
            )
        lines.append("[external-job] Topology runtime_target=" + str(topology.runtime_target))
        lines.append("[external-job] Validation succeeded (local checks only).")
        job.status = "succeeded"
    elif job.mode == "plan":
        lines.append("[external-job] Generating deployment plan (stub — no Terraform/Ansible apply)...")
        plan_ref = {
            "type": "plan_summary",
            "uri": f"stub://external-jobs/{job.id}/plan.json",
            "target_type": target.target_type,
        }
        job.artifact_refs = [plan_ref]
        lines.append(f"[external-job] Plan artifact: {plan_ref['uri']}")
        lines.append("[external-job] Plan succeeded (placeholder artifact only).")
        job.status = "succeeded"

    job.logs = _join_logs(lines)
    job.finished_at = datetime.now(UTC)
    db.flush()


def _join_logs(lines: list[str]) -> str:
    return mask_secrets_in_text("\n".join(lines)) or ""
