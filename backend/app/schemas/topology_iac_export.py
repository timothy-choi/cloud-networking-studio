"""Step 52B: IaC export preview and validation schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IaCExportArtifactItem(BaseModel):
    id: str
    name: str
    type: str
    category: str
    download_path: str


class IaCExportWarningItem(BaseModel):
    severity: str = Field(description="info | warning | error")
    code: str
    message: str
    node_name: str | None = None


class TopologyIacExportPreviewResponse(BaseModel):
    topology_id: UUID
    topology_name: str
    runtime_target: str
    networking_mode: str
    artifacts: list[IaCExportArtifactItem] = Field(default_factory=list)
    previews: dict[str, str] = Field(default_factory=dict)
    terraform_files: list[str] = Field(default_factory=list)
    ansible_files: list[str] = Field(default_factory=list)
    archive_files: list[str] = Field(default_factory=list)
    warnings: list[IaCExportWarningItem] = Field(default_factory=list)
    unsupported_features: list[str] = Field(default_factory=list)
    todo_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
