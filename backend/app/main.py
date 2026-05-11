"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.controller import router as controller_router
from app.api.deployments import router as deployments_router
from app.api.failure_injections import router as failure_injections_router
from app.api.runtime import router as runtime_router
from app.api.topologies import router as topologies_router
from app.api.traffic_tests import router as traffic_tests_router
from app.core.config import settings
from app.db.session import Base, engine

OPENAPI_TAGS_METADATA: list[dict[str, str]] = [
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
        "description": "Inspect live provider state (containers, networks), fetch logs/stats, and run **reconciliation** passes.",
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
    import app.models  # noqa: F401 — register tables on Base.metadata

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description=APP_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS_METADATA,
    lifespan=lifespan,
)

app.include_router(topologies_router)
app.include_router(deployments_router)
app.include_router(runtime_router)
app.include_router(controller_router)
app.include_router(traffic_tests_router)
app.include_router(failure_injections_router)


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
