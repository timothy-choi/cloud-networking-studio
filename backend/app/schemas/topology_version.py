"""Pydantic schemas for topology versions (Step 56)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TopologyVersionCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None


class TopologyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topology_id: UUID
    version_number: int
    name: str | None
    description: str | None
    source: str
    parent_version_id: UUID | None
    created_by_user_id: UUID | None
    created_at: datetime


class TopologyVersionDetailResponse(TopologyVersionResponse):
    snapshot_json: dict = Field(description="Full topology snapshot at this version.")


class TopologyVersionListResponse(BaseModel):
    items: list[TopologyVersionResponse]


class TopologyVersionDiffResponse(BaseModel):
    base_version_id: UUID
    compare_version_id: UUID
    diff: dict


class TopologyVersionRollbackRequest(BaseModel):
    mode: str = Field(
        default="config_only",
        pattern="^(config_only|rollback_and_destroy|rollback_and_redeploy)$",
    )


class RollbackImpactDeploymentItem(BaseModel):
    id: UUID
    status: str
    topology_sync_status: str | None = None


class TopologyVersionRollbackImpact(BaseModel):
    active_deployment_count: int
    active_deployments: list[RollbackImpactDeploymentItem]
    nodes_removed: list[str] = Field(default_factory=list)
    nodes_added: list[str] = Field(default_factory=list)
    services_removed: list[str] = Field(default_factory=list)
    removes_deployed_nodes: bool = False
    nodes_removed_from_runtime: list[str] = Field(default_factory=list)
    target_node_count: int = 0
    current_node_count: int = 0
    warning_message: str | None = None


class TopologyVersionRollbackResponse(BaseModel):
    version: TopologyVersionResponse
    mode: str = "config_only"
    message: str = "Topology restored from snapshot."
    impact: TopologyVersionRollbackImpact | None = None
    destroyed_deployment_ids: list[UUID] = Field(default_factory=list)
    redeployed_deployment_id: UUID | None = None
