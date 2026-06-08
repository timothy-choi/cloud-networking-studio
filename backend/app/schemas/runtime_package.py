"""Runtime package export schemas (Step 65)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimePackageGenerateRequest(BaseModel):
    strategy_id: str = "docker-vm"
    provider: str = "gcp"
    machine_type: str | None = None
    placement_mode: str = "first_fit"
    host_count: int | None = None


class RuntimePackageGenerateResponse(BaseModel):
    package_id: str
    strategy_id: str
    status: str
    files: list[str]
    download_url: str
    planning_only: bool = False
    limitations: list[str] = Field(default_factory=list)
