"""Topology placement planning API routes (Feature 59A)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.infrastructure_deployments import _to_deployment
from app.db.session import get_db
from app.models.user import User
from app.schemas.deployment_strategy import StrategyRecommendationResponse
from app.schemas.topology_placement import (
    GenerateInfrastructureDeploymentRequest,
    GenerateInfrastructureDeploymentResponse,
    PlacementAssignedNode,
    PlacementHost,
    TopologyNodeResourceBreakdown,
    TopologyPlacementPlanResponse,
    TopologyResourceEstimateResponse,
)
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services.deployment_strategy_registry import assert_strategy_available
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services import infrastructure_deployment_service as infra_svc
from app.services import topology_placement_planner_service as placement_svc
from app.services.infra_observability import append_event
from app.services.topology_version_service import load_topology_with_graph

router = APIRouter(tags=["topology-placement"])


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
        placement_unit_count=raw.get("placement_unit_count") or raw["total_replicas"],
        nodes=[TopologyNodeResourceBreakdown(**node) for node in raw.get("nodes") or []],
    )


def _placement_response(raw: dict) -> TopologyPlacementPlanResponse:
    hosts: list[PlacementHost] = []
    for host in raw.get("hosts") or []:
        details = host.get("assigned_node_details") or []
        assigned = host.get("assigned_nodes")
        if assigned and isinstance(assigned[0], dict):
            details = [PlacementAssignedNode(**node) for node in assigned]
            assigned = [node.display_name for node in details]
        elif not assigned and details:
            assigned = [str(node.get("display_name") or node.get("node_name")) for node in details]
        else:
            assigned = [str(name) for name in (assigned or [])]
            details = [PlacementAssignedNode(**node) for node in details]
        hosts.append(
            PlacementHost(
                host_index=int(host["host_index"]),
                machine_type=str(host.get("machine_type") or raw.get("recommended_machine_type") or ""),
                cpu_used=float(host.get("cpu_used") or host.get("estimated_cpu_used") or 0),
                cpu_capacity=float(host.get("cpu_capacity") or 0),
                memory_used_mb=int(host.get("memory_used_mb") or host.get("estimated_memory_used_mb") or 0),
                memory_capacity_mb=int(host.get("memory_capacity_mb") or 0),
                disk_used_gb=float(host.get("disk_used_gb") or 0),
                disk_capacity_gb=float(host.get("disk_capacity_gb") or 30),
                assigned_nodes=assigned,
                assigned_node_details=details,
                estimated_cpu_used=float(host.get("estimated_cpu_used") or host.get("cpu_used") or 0),
                estimated_memory_used_mb=int(
                    host.get("estimated_memory_used_mb") or host.get("memory_used_mb") or 0
                ),
            )
        )
    return TopologyPlacementPlanResponse(
        total_cpu=raw["total_cpu"],
        total_memory_mb=raw["total_memory_mb"],
        total_disk_gb=raw["total_disk_gb"],
        total_replicas=raw["total_replicas"],
        node_count=raw["node_count"],
        workload_node_count=raw["workload_node_count"],
        placement_unit_count=raw.get("placement_unit_count") or raw["total_replicas"],
        provider=raw["provider"],
        recommended_host_count=raw["recommended_host_count"],
        recommended_machine_type=raw["recommended_machine_type"],
        machine_rationale=raw["machine_rationale"],
        hosts=hosts,
        warnings=raw.get("warnings") or [],
        exposed_ports=raw.get("exposed_ports") or [],
        suggested_template_id=raw.get("suggested_template_id") or "docker-vm",
        nodes=[TopologyNodeResourceBreakdown(**node) for node in raw.get("nodes") or []],
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
    return _estimate_response(placement_svc.build_resource_estimate(topology))


@router.get(
    "/topologies/{topology_id}/placement-plan",
    response_model=TopologyPlacementPlanResponse,
)
def get_topology_placement_plan(
    topology_id: UUID,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyPlacementPlanResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        plan = placement_svc.build_placement_plan(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _placement_response(plan)


def _strategy_response(raw: dict) -> StrategyRecommendationResponse:
    return StrategyRecommendationResponse(
        recommended_strategy=raw["recommended_strategy"],
        alternatives=raw.get("alternatives") or [],
        reasons=raw.get("reasons") or [],
        warnings=raw.get("warnings") or [],
        strategies=raw.get("strategies") or [],
        recommended_strategy_detail=raw.get("recommended_strategy_detail"),
        evaluation=raw.get("evaluation"),
    )


@router.get(
    "/topologies/{topology_id}/strategy-recommendation",
    response_model=StrategyRecommendationResponse,
)
def get_topology_strategy_recommendation(
    topology_id: UUID,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyRecommendationResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        raw = strategy_svc.build_strategy_recommendation(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _strategy_response(raw)


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
        strategy_id = (body.template_id or "docker-vm").strip()
        assert_strategy_available(strategy_id)
        template_id = strategy_svc.resolve_template_id_for_strategy(strategy_id)
        draft = placement_svc.build_generate_deployment_payload(
            topology,
            db=db,
            provider=body.provider,
            template_id=template_id,
            machine_type=body.machine_type,
            host_count=body.host_count,
            variables=body.variables,
            credentials_ref=body.credentials_ref,
            name=body.name,
        )
        capacity = draft["capacity_check"]
        if capacity["status"] == "insufficient_capacity":
            raise ValueError(
                capacity["messages"][0] if capacity["messages"] else "Insufficient infrastructure capacity."
            )
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
        plan = draft["placement_plan"]
        placement_summary = draft.get("placement_summary") or {}
        deployment.state_metadata_json = {
            **(deployment.state_metadata_json or {}),
            "topology_placement": plan,
            "placement_summary": placement_summary,
            "topology_capacity": capacity,
            "generated_from_topology": True,
            "deployment_strategy": strategy_id,
            "exposed_ports": plan.get("exposed_ports") or [],
            "recommended_disk_gb": plan.get("total_disk_gb"),
        }
        deployment.events_json = append_event(
            deployment.events_json,
            "generated_from_topology",
            message="Infrastructure deployment generated from topology placement plan",
            metadata={
                "placement_summary": placement_summary,
                "topology_placement": {
                    "recommended_host_count": plan.get("recommended_host_count"),
                    "recommended_machine_type": plan.get("recommended_machine_type"),
                    "host_count": len(plan.get("hosts") or []),
                },
                "topology_capacity": capacity,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(deployment)
    return GenerateInfrastructureDeploymentResponse(
        deployment=_to_deployment(deployment).model_dump(),
        placement_plan=_placement_response(plan),
        capacity_check=capacity,
    )
