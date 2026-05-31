"""Topology-aware infrastructure planning API routes (Feature 58B)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.infrastructure_deployments import _to_deployment
from app.db.session import get_db
from app.models.user import User
from app.schemas.topology_infra_planning import (
    GenerateInfrastructureDeploymentRequest,
    GenerateInfrastructureDeploymentResponse,
    InfrastructureRecommendationsResponse,
    TopologyCapacityCheckResponse,
    TopologyNodeResourceBreakdown,
    TopologyResourceEstimateResponse,
)
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services import infrastructure_deployment_service as infra_svc
from app.services import topology_infra_planning_service as planning_svc
from app.services.infra_observability import append_event
from app.services.topology_version_service import load_topology_with_graph

router = APIRouter(tags=["topology-infra-planning"])


def _load_topology(db: Session, user: User, topology_id: UUID):
    get_topology_for_user(db, user, topology_id)
    topology = load_topology_with_graph(db, topology_id)
    if topology is None:
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


def _capacity_response(raw: dict) -> TopologyCapacityCheckResponse:
    return TopologyCapacityCheckResponse(
        status=raw["status"],
        messages=raw.get("messages") or [],
        resource_estimate=_estimate_response(raw["resource_estimate"]),
        selected_provider=raw["selected_provider"],
        selected_machine_type=raw.get("selected_machine_type"),
        available_memory_mb=raw.get("available_memory_mb"),
        available_cpu=raw.get("available_cpu"),
        required_memory_mb=raw["required_memory_mb"],
        required_cpu=raw["required_cpu"],
    )


@router.get(
    "/topologies/{topology_id}/resource-estimate",
    response_model=TopologyResourceEstimateResponse,
)
def get_topology_resource_estimate(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyResourceEstimateResponse:
    topology = _load_topology(db, user, topology_id)
    return _estimate_response(planning_svc.estimate_topology_resources(topology))


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


@router.post(
    "/topologies/{topology_id}/generate-infrastructure-deployment",
    response_model=GenerateInfrastructureDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_infrastructure_deployment(
    topology_id: UUID,
    body: GenerateInfrastructureDeploymentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GenerateInfrastructureDeploymentResponse:
    require_topology_editor(db, user, topology_id)
    topology = _load_topology(db, user, topology_id)
    try:
        draft = planning_svc.build_generate_deployment_payload(
            topology,
            provider=body.provider,
            template_id=body.template_id,
            machine_type=body.machine_type,
            variables=body.variables,
            credentials_ref=body.credentials_ref,
            name=body.name,
        )
        capacity = draft["capacity_check"]
        if capacity["status"] == "insufficient_capacity":
            raise ValueError(capacity["messages"][0] if capacity["messages"] else "Insufficient infrastructure capacity.")
        deployment = infra_svc.create_deployment(
            db,
            topology=topology,
            actor=user,
            name=draft["name"],
            template_id=draft["template_id"],
            provider=draft["provider"],
            variables=draft["variables"],
            credentials_ref=draft.get("credentials_ref"),
        )
        deployment.state_metadata_json = {
            **(deployment.state_metadata_json or {}),
            "topology_capacity": capacity,
            "generated_from_topology": True,
        }
        deployment.events_json = append_event(
            deployment.events_json,
            "generated_from_topology",
            message="Infrastructure deployment generated from topology resource estimate",
            metadata={
                "topology_capacity": capacity,
                "rationale": draft.get("rationale") or [],
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return GenerateInfrastructureDeploymentResponse(
        deployment=_to_deployment(deployment).model_dump(),
        resource_estimate=_estimate_response(draft["resource_estimate"]),
        recommendations=draft["recommendations"],
        capacity_check=_capacity_response(capacity),
    )
