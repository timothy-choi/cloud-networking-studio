"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit_logs import router as audit_logs_router
from app.api.api_tokens import router as api_tokens_router
from app.api.auth import router as auth_router
from app.api.controller import router as controller_router
from app.api.deployments import router as deployments_router
from app.api.failure_injections import router as failure_injections_router
from app.api.metrics import router as metrics_router
from app.api.platform_metrics import router as platform_metrics_router
from app.api.security_status import router as security_status_router
from app.api.notifications import router as notifications_router
from app.api.onboarding import router as onboarding_router
from app.api.project_invitations import router as project_invitations_router
from app.api.projects import router as projects_router
from app.api.runtime import router as runtime_router
from app.api.terminal import router as terminal_router
from app.api.templates import router as templates_router
from app.api.topologies import router as topologies_router
from app.api.topology_exports import router as topology_exports_router
from app.api.topology_versions import router as topology_versions_router
from app.api.credential_profiles import router as credential_profiles_router
from app.api.deployment_profiles import router as deployment_profiles_router
from app.api.deployment_targets import router as deployment_targets_router
from app.api.external_deployment_jobs import router as external_deployment_jobs_router
from app.api.infrastructure_deployments import router as infrastructure_deployments_router
from app.api.topology_infra_planning import router as topology_infra_planning_router
from app.api.traffic_tests import router as traffic_tests_router
from app.core.config import settings
from app.db.session import Base, engine
from app.core.errors import register_exception_handlers
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.strip_api_prefix import StripApiPrefixMiddleware

OPENAPI_TAGS_METADATA: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": "Register, login, and current user (**JWT** bearer tokens).",
    },
    {
        "name": "api-tokens",
        "description": "Personal **API tokens** (Bearer) for CLI and CI/CD — same project RBAC as interactive users.",
    },
    {
        "name": "credential-profiles",
        "description": "Encrypted **cloud credential profiles** for infrastructure deployments (`credential:<id>` refs).",
    },
    {
        "name": "topology-infra-planning",
        "description": "Topology resource estimates, infrastructure recommendations, and generated deployment drafts (Feature 58B).",
    },
    {
        "name": "projects",
        "description": "Workspaces that own topologies; all lab resources are scoped under projects.",
    },
    {
        "name": "topologies",
        "description": "Persisted graph of networks, nodes, and links—the **desired state** before runtime provisioning.",
    },
    {
        "name": "deployments",
        "description": "Apply topology intent to the configured **runtime provider**, stream **deployment events**, and tear workloads down.",
    },
    {
        "name": "runtime",
        "description": "Inspect live provider state (containers, networks), fetch logs/stats, run **reconciliation** passes, and read **GET /runtime/status** (executor probe).",
    },
    {
        "name": "controller",
        "description": "Manual controller hooks: status, periodic reconcile sweep, and **single-deployment healing**.",
    },
    {
        "name": "traffic-tests",
        "description": "Synthetic **ping** and **HTTP** checks executed between deployed containers.",
    },
    {
        "name": "failure-injections",
        "description": "Controlled disruption (**stop / restart / kill**) for resilience and drift scenarios.",
    },
    {
        "name": "metrics",
        "description": "Cross-topology **observability** counters and recent activity for dashboards (read-only).",
    },
    {
        "name": "templates",
        "description": "Save and reuse **topology/runtime** setups as templates; clone into new drafts.",
    },
    {
        "name": "health",
        "description": "Process-level probes for orchestrators and load balancers.",
    },
]

APP_DESCRIPTION = """\
**Cloud Networking Studio** exposes a control-plane style HTTP API: model infrastructure as a topology graph,
deploy it to Docker networks and containers, validate connectivity with traffic tests, inject failures,
reconcile drift, and heal workloads—backed by PostgreSQL for intent and audit events.

See repository **README** and **docs/** for architecture and demo scripts.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register models and create tables (Alembic replaces create_all later)."""
    from app.db.bootstrap import run_startup_datafixes
    from app.db.startup_schema import import_all_orm_modules, verify_core_schema

    import_all_orm_modules()
    Base.metadata.create_all(bind=engine)
    verify_core_schema(engine)
    run_startup_datafixes(engine)
    from app.core.security_validation import run_startup_security_checks

    run_startup_security_checks(settings)
    from app.db.session import SessionLocal
    from app.services.cleanup_service import expire_stale_terminal_sessions

    with SessionLocal() as db:
        expire_stale_terminal_sessions(db)
        db.commit()
    from app.services.remote_ssh_runtime import log_remote_ssh_runtime_status

    log_remote_ssh_runtime_status()
    yield


app = FastAPI(
    title=settings.app_name,
    description=APP_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS_METADATA,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(api_tokens_router)
app.include_router(projects_router)
app.include_router(project_invitations_router)
app.include_router(topologies_router)
app.include_router(topology_versions_router)
app.include_router(deployment_profiles_router)
app.include_router(credential_profiles_router)
app.include_router(deployment_targets_router)
app.include_router(external_deployment_jobs_router)
app.include_router(infrastructure_deployments_router)
app.include_router(topology_infra_planning_router)
app.include_router(topology_exports_router)
app.include_router(templates_router)
app.include_router(deployments_router)
app.include_router(terminal_router)
app.include_router(runtime_router)
app.include_router(controller_router)
app.include_router(traffic_tests_router)
app.include_router(failure_injections_router)
app.include_router(metrics_router)
app.include_router(platform_metrics_router)
app.include_router(security_status_router)
app.include_router(onboarding_router)
app.include_router(notifications_router)
app.include_router(audit_logs_router)


def _cors_origins() -> list[str]:
    parts = [p.strip() for p in settings.cors_origins.split(",") if p.strip()]
    return parts or ["http://localhost:5174", "http://127.0.0.1:5174"]


_cors_kw: dict = {
    "allow_origins": _cors_origins(),
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if (rx := (settings.cors_origin_regex or "").strip()):
    _cors_kw["allow_origin_regex"] = rx

app.add_middleware(CORSMiddleware, **_cors_kw)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(StripApiPrefixMiddleware)


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness / readiness",
    response_description="Service identity and environment name (does not probe Postgres or Docker).",
    responses={
        200: {
            "description": "API process is healthy.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "service": "Cloud Networking Studio",
                        "environment": "development",
                    }
                }
            },
        }
    },
)
def health() -> dict[str, str]:
    """Return a minimal JSON payload suitable for orchestrator health checks."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }
