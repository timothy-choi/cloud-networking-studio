"""Background runner for post-apply host configuration."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from uuid import UUID

from app.db.session import SessionLocal
from app.models.infrastructure_deployment import InfrastructureDeployment
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.infra_observability import append_event

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_jobs: set[UUID] = set()


def is_configuration_job_running(deployment_id: UUID) -> bool:
    with _lock:
        return deployment_id in _active_jobs


def enqueue_host_configuration(*, deployment_id: UUID, actor_user_id: UUID) -> bool:
    """Start configuration in the background unless already running."""
    with _lock:
        if deployment_id in _active_jobs:
            return False
        _active_jobs.add(deployment_id)

    if os.environ.get("CNS_SYNC_INFRA_CONFIGURATION") == "1":
        try:
            _run_configuration_job(deployment_id=deployment_id, actor_user_id=actor_user_id)
        finally:
            with _lock:
                _active_jobs.discard(deployment_id)
        return True

    thread = threading.Thread(
        target=_run_configuration_job_wrapper,
        args=(deployment_id, actor_user_id),
        name=f"infra-config-{deployment_id}",
        daemon=True,
    )
    thread.start()
    return True


def _run_configuration_job_wrapper(deployment_id: UUID, actor_user_id: UUID) -> None:
    try:
        _run_configuration_job(deployment_id=deployment_id, actor_user_id=actor_user_id)
    except Exception:
        logger.exception("Host configuration job failed for deployment %s", deployment_id)
    finally:
        with _lock:
            _active_jobs.discard(deployment_id)


def _run_configuration_job(*, deployment_id: UUID, actor_user_id: UUID) -> None:
    from app.services import infrastructure_deployment_service as infra_svc

    with SessionLocal() as db:
        deployment = db.get(InfrastructureDeployment, deployment_id)
        actor = db.get(User, actor_user_id)
        if deployment is None or actor is None:
            return

        meta = dict(deployment.state_metadata_json or {})
        meta["configuration_job_status"] = "running"
        meta["configuration_started_at"] = datetime.now(UTC).isoformat()
        deployment.state_metadata_json = meta
        deployment.status = "configuring"
        db.commit()

        final_status = deployment.status
        try:
            configuration_status, configuration_error = infra_svc._run_host_configuration(
                db,
                deployment=deployment,
            )
            infra_svc._finalize_after_configuration(
                db,
                deployment=deployment,
                actor=actor,
                configuration_status=configuration_status,
                configuration_error=configuration_error,
            )
            meta = dict(deployment.state_metadata_json or {})
            meta["configuration_job_status"] = "completed" if configuration_status == "completed" else "failed"
            deployment.state_metadata_json = meta
            final_status = deployment.status
        except Exception as exc:
            deployment.status = "configuration_failed"
            deployment.error_message = str(exc)
            deployment.events_json = append_event(
                deployment.events_json,
                "configure_failed",
                message=str(exc),
            )
            meta = dict(deployment.state_metadata_json or {})
            meta["configuration_job_status"] = "failed"
            deployment.state_metadata_json = meta
            final_status = deployment.status

        db.commit()
        record_audit(
            db,
            action="infrastructure_deployment.configure",
            resource_type="infrastructure_deployment",
            resource_id=deployment.id,
            project_id=deployment.project_id,
            actor_user_id=actor.id,
            status=final_status,
        )
        db.commit()
