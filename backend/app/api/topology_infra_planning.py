"""Topology-aware infrastructure planning API routes (Feature 58B).

Resource estimate, placement plan, and deployment generation are served by
``topology_placement`` (Feature 59A/59B). This router retains multi-cloud
recommendations only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.topology_infra_planning import (
    InfrastructureRecommendationsResponse,
    TopologyNodeResourceBreakdown,
    TopologyResourceEstimateResponse,
)
from app.services.access_control import get_topology_for_user
from app.services import topology_infra_planning_service as planning_svc
from app.services.topology_version_service import load_topology_with_graph

router = APIRouter(tags=["topology-infra-planning"])


def _load_topology(db: Session, user: User, topology_id: UUID):
    get_topology_for_user(db, user, topology_id)
    topology = load_topology_with_graph(db, topology_id)
    if topology is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Topology not found")
    return topology


def _estimate_response(raw: dict) -> TopologyResourceEstimateResponse:
    return TopologyResourceEstimateResponse(
        total_cpu=raw["total_cpu"],
        total_memory_mb=raw["total_memory_mb"],
        total_disk_gb=raw["total_disk_gb"],
        total_replicas=raw["total_replicas"],
        node_count=raw["node_count"],
        workload_node_count=raw["workload_node_count"],
        nodes=[TopologyNodeResourceBreakdown(**node) for node in raw.get("nodes") or []],
    )


@router.get(
    "/topologies/{topology_id}/infrastructure-recommendations",
    response_model=InfrastructureRecommendationsResponse,
)
def get_topology_infrastructure_recommendations(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InfrastructureRecommendationsResponse:
    topology = _load_topology(db, user, topology_id)
    raw = planning_svc.build_infrastructure_recommendations(topology)
    return InfrastructureRecommendationsResponse(
        resource_estimate=_estimate_response(raw["resource_estimate"]),
        recommendations=raw["recommendations"],
        suggested_template_id=raw["suggested_template_id"],
        suggested_provider=raw["suggested_provider"],
        suggested_variables=raw["suggested_variables"],
        rationale=raw.get("rationale") or [],
    )
