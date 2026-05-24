"""Project and user quota checks (Step 53B)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_token import ApiToken
from app.models.deployment import Deployment, DeploymentStatus
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.topology import Topology, TopologyNode
from app.services.deployment_queries import deployment_status_blocks_new_deploy


def _quota_exceeded(
    quota: str,
    message: str,
    *,
    db: Session | None = None,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    **details: object,
) -> HTTPException:
    if db is not None and user_id is not None:
        try:
            from app.services.notification_service import notify_quota_exceeded_event

            notify_quota_exceeded_event(
                db,
                user_id=user_id,
                project_id=project_id,
                quota=quota,
                message=message,
            )
        except Exception:
            pass
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "QUOTA_EXCEEDED",
            "message": message,
            "quota": quota,
            **details,
        },
    )


def count_active_deployments_for_project(db: Session, project_id: UUID) -> int:
    blocking = (
        DeploymentStatus.PENDING,
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.STOPPING,
        DeploymentStatus.SUCCEEDED,
    )
    return int(
        db.scalar(
            select(func.count())
            .select_from(Deployment)
            .join(Topology, Deployment.topology_id == Topology.id)
            .where(Topology.project_id == project_id, Deployment.status.in_(blocking))
        )
        or 0
    )


def count_nodes_for_topology(db: Session, topology_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(TopologyNode).where(TopologyNode.topology_id == topology_id)
        )
        or 0
    )


def count_services_for_deployment(db: Session, deployment_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeResource)
            .where(
                DeploymentRuntimeResource.deployment_id == deployment_id,
                DeploymentRuntimeResource.resource_type == "service",
            )
        )
        or 0
    )


def count_active_terminal_sessions_for_user(db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeTerminalSession)
            .where(
                DeploymentRuntimeTerminalSession.user_id == user_id,
                DeploymentRuntimeTerminalSession.status.in_(("opening", "active")),
            )
        )
        or 0
    )


def count_api_tokens_for_user(db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        )
        or 0
    )


def quota_limits() -> dict[str, int]:
    return {
        "max_active_deployments_per_project": settings.quota_max_active_deployments_per_project,
        "max_nodes_per_topology": settings.quota_max_nodes_per_topology,
        "max_services_per_deployment": settings.quota_max_services_per_deployment,
        "max_terminal_sessions_per_user": settings.terminal_max_sessions_per_user,
        "max_api_tokens_per_user": settings.quota_max_api_tokens_per_user,
    }


def build_project_quota_usage(db: Session, project_id: UUID, user_id: UUID) -> dict:
    limits = quota_limits()
    active_deployments = count_active_deployments_for_project(db, project_id)
    terminal_sessions = count_active_terminal_sessions_for_user(db, user_id)
    api_tokens = count_api_tokens_for_user(db, user_id)
    return {
        "project_id": str(project_id),
        "limits": limits,
        "usage": {
            "active_deployments": active_deployments,
            "terminal_sessions": terminal_sessions,
            "api_tokens": api_tokens,
        },
        "remaining": {
            "active_deployments": max(0, limits["max_active_deployments_per_project"] - active_deployments),
            "terminal_sessions": max(0, limits["max_terminal_sessions_per_user"] - terminal_sessions),
            "api_tokens": max(0, limits["max_api_tokens_per_user"] - api_tokens),
        },
    }


def ensure_can_deploy_project(
    db: Session, project_id: UUID, *, user_id: UUID | None = None
) -> None:
    limit = settings.quota_max_active_deployments_per_project
    used = count_active_deployments_for_project(db, project_id)
    if used >= limit:
        raise _quota_exceeded(
            "active_deployments",
            f"Project active deployment quota reached ({used}/{limit}). Destroy a deployment before deploying again.",
            db=db,
            user_id=user_id,
            project_id=project_id,
            used=used,
            limit=limit,
        )


def ensure_topology_node_quota(
    db: Session,
    topology_id: UUID,
    *,
    adding: int = 1,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
) -> None:
    limit = settings.quota_max_nodes_per_topology
    used = count_nodes_for_topology(db, topology_id)
    if used + adding > limit:
        raise _quota_exceeded(
            "nodes_per_topology",
            f"Topology node quota reached ({used}/{limit}). Remove nodes before adding more.",
            db=db,
            user_id=user_id,
            project_id=project_id,
            used=used,
            limit=limit,
        )


def ensure_deployment_service_quota(db: Session, deployment_id: UUID, *, adding: int = 1) -> None:
    limit = settings.quota_max_services_per_deployment
    used = count_services_for_deployment(db, deployment_id)
    if used + adding > limit:
        raise _quota_exceeded(
            "services_per_deployment",
            f"Deployment service quota reached ({used}/{limit}).",
            used=used,
            limit=limit,
        )


def ensure_terminal_session_quota(db: Session, user_id: UUID) -> None:
    limit = settings.terminal_max_sessions_per_user
    used = count_active_terminal_sessions_for_user(db, user_id)
    if used >= limit:
        raise _quota_exceeded(
            "terminal_sessions",
            f"Terminal session quota reached ({used}/{limit}). Close an existing session first.",
            db=db,
            user_id=user_id,
            used=used,
            limit=limit,
        )


def ensure_api_token_quota(db: Session, user_id: UUID) -> None:
    limit = settings.quota_max_api_tokens_per_user
    used = count_api_tokens_for_user(db, user_id)
    if used >= limit:
        raise _quota_exceeded(
            "api_tokens",
            f"API token quota reached ({used}/{limit}). Revoke an unused token first.",
            db=db,
            user_id=user_id,
            used=used,
            limit=limit,
        )
