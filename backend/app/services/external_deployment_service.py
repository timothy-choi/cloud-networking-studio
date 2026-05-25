"""External deployment persistence (Step 57B)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.external_deployment import ExternalDeployment


def list_external_deployments_for_topology(
    db: Session,
    topology_id: UUID,
) -> list[ExternalDeployment]:
    return list(
        db.scalars(
            select(ExternalDeployment)
            .where(ExternalDeployment.topology_id == topology_id)
            .order_by(ExternalDeployment.created_at.desc())
        ).all()
    )


def get_external_deployment(db: Session, deployment_id: UUID) -> ExternalDeployment | None:
    return db.get(ExternalDeployment, deployment_id)


def get_active_external_deployment(
    db: Session,
    *,
    topology_id: UUID,
    target_id: UUID,
) -> ExternalDeployment | None:
    return db.scalar(
        select(ExternalDeployment)
        .where(
            ExternalDeployment.topology_id == topology_id,
            ExternalDeployment.target_id == target_id,
            ExternalDeployment.status == "active",
        )
        .order_by(ExternalDeployment.created_at.desc())
        .limit(1)
    )


def create_external_deployment(
    db: Session,
    *,
    project_id: UUID,
    topology_id: UUID,
    target_id: UUID,
    job_id: UUID,
    compose_project_name: str,
    remote_workdir: str,
    services_json: list[dict],
    metadata_json: dict,
) -> ExternalDeployment:
    row = ExternalDeployment(
        project_id=project_id,
        topology_id=topology_id,
        target_id=target_id,
        job_id=job_id,
        compose_project_name=compose_project_name,
        remote_workdir=remote_workdir,
        status="active",
        services_json=services_json,
        metadata_json=metadata_json,
    )
    db.add(row)
    db.flush()
    return row


def mark_external_deployment_destroyed(db: Session, deployment: ExternalDeployment) -> ExternalDeployment:
    deployment.status = "destroyed"
    deployment.destroyed_at = datetime.now(UTC)
    db.flush()
    return deployment
