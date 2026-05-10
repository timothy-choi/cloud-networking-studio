"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deployments import router as deployments_router
from app.api.topologies import router as topologies_router
from app.core.config import settings
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register models and create tables (Alembic replaces create_all later)."""
    import app.models  # noqa: F401 — register tables on Base.metadata

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(topologies_router)
app.include_router(deployments_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness-style probe; does not check downstream dependencies."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }
