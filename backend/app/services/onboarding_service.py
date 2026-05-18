"""Onboarding progress, auto-detection, and optional one-click demo (Step 46)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment, DeploymentStatus
from app.models.deployment_runtime_exec_result import DeploymentRuntimeExecResult
from app.models.deployment_runtime_resource import DeploymentRuntimeResource
from app.models.deployment_service_exposure import DeploymentServiceExposure
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.runtime_template import RuntimeTemplate
from app.models.topology import Topology
from app.models.traffic_test import TrafficTest, TrafficTestStatus
from app.models.user import User
from app.models.user_onboarding import UserOnboarding
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    OnboardingStatusUpdate,
    OnboardingStepResponse,
    StartDemoResponse,
)
from app.schemas.template import TemplateCloneRequest
from app.services import template_service as tmpl_svc
from app.services import topology_deploy_execution
from app.services.deployment_queries import active_deployment_blocking_new_deploy

# Built-in starter used by the demo flow — seeded in ``ensure_starter_runtime_templates``.
DEMO_TEMPLATE_SLUG = "client-service"
DEMO_PROJECT_NAME = "CNS Quick demo"
DEMO_TOPOLOGY_NAME = "CNS demo topology (starter)"

STEP_PROJECT = "project"
STEP_TOPOLOGY = "topology"
STEP_DEPLOY = "deploy"
STEP_RUNTIME_ACCESS = "runtime_access"
STEP_EXPOSE_SERVICE = "expose_service"
STEP_HEALTH_CHECK = "health_check"
STEP_SAFE_EXEC = "safe_exec"
STEP_DESTROY_DEPLOYMENT = "destroy_deployment"


_ONBOARDING_CATALOG: list[dict[str, str]] = [
    {
        "id": STEP_PROJECT,
        "title": "Create or select a project",
        "description": "Projects scope topologies and deployments. Registration creates a starter workspace.",
    },
    {
        "id": STEP_TOPOLOGY,
        "title": "Create a topology or choose a template",
        "description": "Model nodes and links, or clone a starter template from the library.",
    },
    {
        "id": STEP_DEPLOY,
        "title": "Deploy topology",
        "description": "Apply the graph to Docker (or Kubernetes) so workloads exist in the runtime provider.",
    },
    {
        "id": STEP_RUNTIME_ACCESS,
        "title": "Open Runtime Access",
        "description": "Inspect live resources, internal URLs, and operations for the active deployment.",
    },
    {
        "id": STEP_EXPOSE_SERVICE,
        "title": "Expose a service",
        "description": "Publish a workload port so you can reach it from your machine or CI.",
    },
    {
        "id": STEP_HEALTH_CHECK,
        "title": "Run a health check or traffic test",
        "description": "Validate reachability from Runtime Operations or save a traffic test on the topology.",
    },
    {
        "id": STEP_SAFE_EXEC,
        "title": "Try safe exec",
        "description": "Run an allowlisted diagnostic command inside a workload via Runtime Operations.",
    },
    {
        "id": STEP_DESTROY_DEPLOYMENT,
        "title": "Destroy deployment",
        "description": "Tear down runtime resources when you are finished to free capacity.",
    },
]


def _persistent_completed_ids(row: UserOnboarding) -> set[str]:
    return {str(s).strip() for s in (row.completed_steps or []) if str(s).strip()}


def _ordered_completed_list(merged: set[str]) -> list[str]:
    catalog_ids = [e["id"] for e in _ONBOARDING_CATALOG]
    out = [sid for sid in catalog_ids if sid in merged]
    extras = sorted(sid for sid in merged if sid not in set(catalog_ids))
    return out + extras


def _project_ids_for_user(db: Session, user_id: UUID) -> list[UUID]:
    rows = db.scalars(select(ProjectMembership.project_id).where(ProjectMembership.user_id == user_id)).all()
    return list(rows)


def _auto_detected(db: Session, user: User) -> dict[str, bool]:
    pids = _project_ids_for_user(db, user.id)
    if not pids:
        return {entry["id"]: False for entry in _ONBOARDING_CATALOG}

    def q_count(*conds: Any) -> int:
        stmt = select(func.count()).select_from(Deployment).join(Topology, Topology.id == Deployment.topology_id)
        stmt = stmt.where(and_(Topology.project_id.in_(pids), *conds))
        return int(db.scalar(stmt) or 0)

    has_topology = int(
        db.scalar(select(func.count()).select_from(Topology).where(Topology.project_id.in_(pids))) or 0
    ) > 0

    has_succeeded_deploy = q_count(Deployment.status == DeploymentStatus.SUCCEEDED) > 0

    has_runtime_rows = int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeResource)
            .join(Deployment, Deployment.id == DeploymentRuntimeResource.deployment_id)
            .join(Topology, Topology.id == Deployment.topology_id)
            .where(
                Topology.project_id.in_(pids),
                Deployment.status == DeploymentStatus.SUCCEEDED,
            )
        )
        or 0
    ) > 0

    has_exposure = int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentServiceExposure)
            .join(Deployment, Deployment.id == DeploymentServiceExposure.deployment_id)
            .join(Topology, Topology.id == Deployment.topology_id)
            .where(Topology.project_id.in_(pids))
        )
        or 0
    ) > 0

    has_health_or_traffic = int(
        db.scalar(
            select(func.count())
            .select_from(TrafficTest)
            .join(Topology, Topology.id == TrafficTest.topology_id)
            .where(
                Topology.project_id.in_(pids),
                TrafficTest.status == TrafficTestStatus.SUCCEEDED,
                TrafficTest.deployment_id.isnot(None),
            )
        )
        or 0
    ) > 0

    has_exec = int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeExecResult)
            .join(Deployment, Deployment.id == DeploymentRuntimeExecResult.deployment_id)
            .join(Topology, Topology.id == Deployment.topology_id)
            .where(Topology.project_id.in_(pids))
        )
        or 0
    ) > 0

    has_stopped = q_count(Deployment.status == DeploymentStatus.STOPPED) > 0

    return {
        STEP_PROJECT: True,
        STEP_TOPOLOGY: has_topology,
        STEP_DEPLOY: has_succeeded_deploy,
        STEP_RUNTIME_ACCESS: has_succeeded_deploy and has_runtime_rows,
        STEP_EXPOSE_SERVICE: has_exposure,
        STEP_HEALTH_CHECK: has_health_or_traffic,
        STEP_SAFE_EXEC: has_exec,
        STEP_DESTROY_DEPLOYMENT: has_stopped,
    }


def get_or_create_onboarding_row(db: Session, user_id: UUID) -> UserOnboarding:
    row = db.get(UserOnboarding, user_id)
    if row is None:
        row = UserOnboarding(user_id=user_id, has_seen_onboarding=False, completed_steps=[])
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def build_status_response(
    db: Session,
    user: User,
    *,
    persist_auto_merge: bool = True,
) -> OnboardingStatusResponse:
    """Return checklist state.

    When ``persist_auto_merge`` is true (default), union live auto-detection into ``completed_steps`` and
    persist so completions are sticky across later state loss (e.g. destroy). When false (used right
    after reset), do not write auto-detections to the DB; still show live auto in per-step ``completed``
    for display so the response matches the pre-reset UX.
    """
    row = get_or_create_onboarding_row(db, user.id)
    auto = _auto_detected(db, user)
    persistent_before = _persistent_completed_ids(row)
    if persist_auto_merge:
        merged = persistent_before | {sid for sid, ok in auto.items() if ok}
        ordered = _ordered_completed_list(merged)
        if set(ordered) != persistent_before:
            row.completed_steps = ordered
            db.commit()
            db.refresh(row)

    persistent_db = _persistent_completed_ids(row)
    if persist_auto_merge:
        display_done = persistent_db
    else:
        display_done = persistent_db | {sid for sid, ok in auto.items() if ok}

    steps: list[OnboardingStepResponse] = []
    for entry in _ONBOARDING_CATALOG:
        sid = entry["id"]
        done = sid in display_done
        steps.append(
            OnboardingStepResponse(
                id=sid,
                title=entry["title"],
                description=entry["description"],
                completed=done,
                auto_detected=bool(auto.get(sid)) and sid not in persistent_before,
            )
        )
    return OnboardingStatusResponse(
        has_seen_onboarding=bool(row.has_seen_onboarding),
        completed_steps=sorted(persistent_db),
        steps=steps,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_onboarding_status(db: Session, user: User, body: OnboardingStatusUpdate) -> OnboardingStatusResponse:
    row = get_or_create_onboarding_row(db, user.id)
    if body.has_seen_onboarding is not None:
        row.has_seen_onboarding = body.has_seen_onboarding
    if body.completed_steps is not None:
        cur = {str(s).strip() for s in body.completed_steps if str(s).strip()}
        row.completed_steps = _ordered_completed_list(cur)
    db.commit()
    db.refresh(row)
    return build_status_response(db, user)


def complete_onboarding_step(db: Session, user: User, step: str) -> OnboardingStatusResponse:
    valid = {e["id"] for e in _ONBOARDING_CATALOG}
    sid = step.strip()
    if sid not in valid:
        raise ValueError("unknown step id")
    row = get_or_create_onboarding_row(db, user.id)
    cur = _persistent_completed_ids(row)
    cur.add(sid)
    row.completed_steps = _ordered_completed_list(cur)
    db.commit()
    db.refresh(row)
    return build_status_response(db, user)


def reset_onboarding(db: Session, user: User) -> OnboardingStatusResponse:
    row = get_or_create_onboarding_row(db, user.id)
    row.has_seen_onboarding = False
    row.completed_steps = []
    db.commit()
    db.refresh(row)
    return build_status_response(db, user, persist_auto_merge=False)


def _get_or_create_demo_project(db: Session, user: User) -> Project:
    stmt = (
        select(Project)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .where(ProjectMembership.user_id == user.id, Project.name == DEMO_PROJECT_NAME)
        .limit(1)
    )
    proj = db.scalar(stmt)
    if proj is not None:
        return proj
    proj = Project(
        owner_user_id=user.id,
        name=DEMO_PROJECT_NAME,
        description="Optional workspace for the one-click demo flow.",
    )
    db.add(proj)
    db.flush()
    db.add(ProjectMembership(project_id=proj.id, user_id=user.id, role="owner"))
    db.flush()
    return proj


def start_demo(
    db: Session,
    user: User,
) -> StartDemoResponse | JSONResponse:
    """Clone the starter template into the demo project and deploy (or resume an active deployment)."""
    tid = db.scalar(select(RuntimeTemplate.id).where(RuntimeTemplate.slug == DEMO_TEMPLATE_SLUG))
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Starter template '{DEMO_TEMPLATE_SLUG}' is not available. Restart the API to run template seeds.",
        )

    proj = _get_or_create_demo_project(db, user)
    topo = db.scalar(
        select(Topology).where(Topology.project_id == proj.id, Topology.name == DEMO_TOPOLOGY_NAME).limit(1)
    )
    if topo is None:
        try:
            topo = tmpl_svc.clone_template_to_topology(
                db,
                user,
                tid,
                TemplateCloneRequest(project_id=proj.id, name=DEMO_TOPOLOGY_NAME),
            )
            db.flush()
            db.refresh(topo)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    blocker = active_deployment_blocking_new_deploy(db, topo.id)
    if blocker is not None:
        db.commit()
        return StartDemoResponse(
            project_id=proj.id,
            topology_id=topo.id,
            deployment_id=blocker.id,
            resumed=True,
            detail="An active deployment already exists for the demo topology; opening it instead of redeploying.",
        )

    out = topology_deploy_execution.execute_topology_deploy(db, user, topo.id)
    if isinstance(out, JSONResponse):
        return out

    dep = out
    return StartDemoResponse(
        project_id=proj.id,
        topology_id=topo.id,
        deployment_id=dep.id,
        resumed=False,
        detail=None,
    )
