"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness-style probe; does not check downstream dependencies."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }
