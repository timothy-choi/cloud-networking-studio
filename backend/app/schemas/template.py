"""API schemas for runtime topology templates (Step 43)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TemplateFromTopologyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None)
    category: str = Field(default="general", max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=50)
    visibility: Literal["private", "project"]


class TemplateCloneRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    project_id: UUID | None = Field(
        default=None,
        description="Target project for the new topology; defaults to first editable project.",
    )


class RuntimeTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    category: str
    tags: list[str]
    owner_user_id: UUID | None
    project_id: UUID | None
    visibility: str
    source_topology_id: UUID | None = None
    slug: str | None = None
    created_at: datetime
    updated_at: datetime
    can_delete: bool = False


class RuntimeTemplateDetailResponse(RuntimeTemplateResponse):
    topology_snapshot: dict[str, Any]
