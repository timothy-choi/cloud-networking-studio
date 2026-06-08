"""Topology placement planning API routes (Feature 59A)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.infrastructure_deployments import _to_deployment
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_infrastructure_advice import (
    AiInfrastructureAdviceRequest,
    AiInfrastructureAdviceResponse,
    RecommendedOverrides,
)
from app.schemas.cost_capacity import CostCapacityAnalysisResponse
from app.schemas.deployment_strategy import StrategyRecommendationResponse
from app.schemas.runtime_strategy import (
    RuntimeRequirementItem,
    RuntimeStrategyCapabilities,
    RuntimeStrategyListResponse,
    RuntimeStrategyPlanResponse,
    RuntimeStrategyResponse,
)
from app.schemas.topology_placement import (
    GenerateInfrastructureDeploymentRequest,
    GenerateInfrastructureDeploymentResponse,
    PlacementAssignedNode,
    PlacementConstraintCreate,
    PlacementConstraintListResponse,
    PlacementConstraintResponse,
    PlacementHost,
    TopologyNodeResourceBreakdown,
    TopologyPlacementPlanResponse,
    TopologyResourceEstimateResponse,
)
from app.services.access_control import get_topology_for_user, require_topology_editor
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services.runtime_strategy_registry import assert_runtime_strategy_for_generation, list_runtime_strategies, runtime_strategy_to_dict
from app.services import runtime_strategy_plan_service as runtime_strategy_svc
from app.services import ai_infrastructure_advisor_service as advisor_svc
from app.services import cost_capacity_advisor_service as cost_capacity_svc
from app.services import infrastructure_deployment_service as infra_svc
from app.services import topology_placement_persistence_service as placement_persist_svc
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
        id=raw.get("id"),
        total_cpu=raw["total_cpu"],
        total_memory_mb=raw["total_memory_mb"],
        total_disk_gb=raw["total_disk_gb"],
        total_replicas=raw["total_replicas"],
        node_count=raw["node_count"],
        workload_node_count=raw["workload_node_count"],
        placement_unit_count=raw.get("placement_unit_count") or raw["total_replicas"],
        provider=raw["provider"],
        placement_mode=raw.get("placement_mode") or "first_fit",
        recommended_host_count=raw["recommended_host_count"],
        host_count=raw.get("host_count") or raw["recommended_host_count"],
        recommended_machine_type=raw["recommended_machine_type"],
        machine_rationale=raw["machine_rationale"],
        hosts=hosts,
        placements=hosts,
        warnings=raw.get("warnings") or [],
        exposed_ports=raw.get("exposed_ports") or [],
        suggested_template_id=raw.get("suggested_template_id") or "docker-vm",
        nodes=[TopologyNodeResourceBreakdown(**node) for node in raw.get("nodes") or []],
        constraints_used=raw.get("constraints_used") or [],
    )


@router.get("/runtime-strategies", response_model=RuntimeStrategyListResponse)
def list_runtime_strategies_endpoint() -> RuntimeStrategyListResponse:
    return RuntimeStrategyListResponse(
        items=[RuntimeStrategyResponse(**runtime_strategy_to_dict(row)) for row in list_runtime_strategies()]
    )


def _runtime_strategy_plan_response(raw: dict) -> RuntimeStrategyPlanResponse:
    strategy = raw.get("runtime_strategy") or {}
    capabilities = raw.get("capabilities") or {}
    return RuntimeStrategyPlanResponse(
        recommended_runtime_strategy=raw["recommended_runtime_strategy"],
        selected_runtime_strategy=raw["selected_runtime_strategy"],
        runtime_strategy=RuntimeStrategyResponse(**strategy),
        capabilities=RuntimeStrategyCapabilities(**capabilities),
        runtime_target_requirements=[
            RuntimeRequirementItem(**item) for item in (raw.get("runtime_target_requirements") or [])
        ],
        deployment_requirements=[RuntimeRequirementItem(**item) for item in (raw.get("deployment_requirements") or [])],
        unsupported_features=raw.get("unsupported_features") or [],
        can_generate_infrastructure=bool(raw.get("can_generate_infrastructure")),
        generation_block_reason=raw.get("generation_block_reason"),
        host_count=int(raw.get("host_count") or 0),
        placement_constraints_count=int(raw.get("placement_constraints_count") or 0),
    )


@router.get(
    "/topologies/{topology_id}/runtime-strategy-plan",
    response_model=RuntimeStrategyPlanResponse,
)
def get_topology_runtime_strategy_plan(
    topology_id: UUID,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    placement_mode: str = "first_fit",
    selected_strategy: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RuntimeStrategyPlanResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        raw = runtime_strategy_svc.build_runtime_strategy_plan_for_topology(
            topology,
            db=db,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            placement_mode=placement_mode,
            selected_strategy_id=selected_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _runtime_strategy_plan_response(raw)


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
    placement_mode: str = "first_fit",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyPlacementPlanResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        constraints = placement_persist_svc.constraints_as_dicts(db, topology_id)
        plan = placement_svc.build_placement_plan(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            placement_mode=placement_mode,
            constraints=constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _placement_response(plan)


def _constraint_response(row) -> PlacementConstraintResponse:
    return PlacementConstraintResponse(
        id=str(row.id),
        topology_id=str(row.topology_id),
        constraint_type=row.constraint_type,
        node_a=row.node_a,
        node_b=row.node_b,
        preferred_host=row.preferred_host,
        created_at=row.created_at,
    )


@router.get(
    "/topologies/{topology_id}/placement-constraints",
    response_model=PlacementConstraintListResponse,
)
def get_topology_placement_constraints(
    topology_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlacementConstraintListResponse:
    _load_topology(db, user, topology_id)
    return PlacementConstraintListResponse(
        items=[_constraint_response(row) for row in placement_persist_svc.list_constraints(db, topology_id)]
    )


@router.post(
    "/topologies/{topology_id}/placement-constraints",
    response_model=PlacementConstraintResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_topology_placement_constraint(
    topology_id: UUID,
    body: PlacementConstraintCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlacementConstraintResponse:
    topology = _load_topology(db, user, topology_id)
    if body.constraint_type in {"same_host", "different_host"} and not body.node_b:
        raise HTTPException(status_code=400, detail=f"{body.constraint_type} requires node_b.")
    if body.constraint_type == "preferred_host" and not body.preferred_host:
        raise HTTPException(status_code=400, detail="preferred_host requires preferred_host.")
    row = placement_persist_svc.create_constraint(
        db,
        topology_id=topology.id,
        project_id=topology.project_id,
        actor=user,
        constraint_type=body.constraint_type,
        node_a=body.node_a,
        node_b=body.node_b,
        preferred_host=body.preferred_host,
    )
    db.commit()
    db.refresh(row)
    return _constraint_response(row)


@router.delete(
    "/topologies/{topology_id}/placement-constraints/{constraint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_topology_placement_constraint(
    topology_id: UUID,
    constraint_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    topology = _load_topology(db, user, topology_id)
    require_topology_editor(db, user, topology.id)
    deleted = placement_persist_svc.delete_constraint(
        db,
        topology_id=topology.id,
        constraint_id=constraint_id,
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Placement constraint not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/topologies/{topology_id}/multi-host-placement-plan",
    response_model=TopologyPlacementPlanResponse,
)
def get_topology_multi_host_placement_plan(
    topology_id: UUID,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    placement_mode: str = "balanced",
    persist: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TopologyPlacementPlanResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        constraints = placement_persist_svc.constraints_as_dicts(db, topology_id)
        plan = placement_svc.build_placement_plan(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            placement_mode=placement_mode,
            constraints=constraints,
        )
        if persist:
            placement_persist_svc.save_plan(
                db,
                topology_id=topology.id,
                project_id=topology.project_id,
                actor=user,
                plan=plan,
            )
            db.commit()
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
    placement_mode: str = "first_fit",
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
            placement_mode=placement_mode,
            constraints=placement_persist_svc.constraints_as_dicts(db, topology_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _strategy_response(raw)


@router.get(
    "/topologies/{topology_id}/cost-capacity-analysis",
    response_model=CostCapacityAnalysisResponse,
)
def get_topology_cost_capacity_analysis(
    topology_id: UUID,
    provider: str = "gcp",
    machine_type: str | None = None,
    host_count: int | None = None,
    placement_mode: str = "first_fit",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CostCapacityAnalysisResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        plan = placement_svc.build_placement_plan(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            placement_mode=placement_mode,
            constraints=placement_persist_svc.constraints_as_dicts(db, topology_id),
        )
        strategy_rec = strategy_svc.build_strategy_recommendation(
            topology,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            placement_mode=placement_mode,
            constraints=placement_persist_svc.constraints_as_dicts(db, topology_id),
        )
        analysis = cost_capacity_svc.build_cost_capacity_analysis(
            plan,
            provider=provider,
            machine_type=machine_type,
            host_count=host_count,
            runtime_strategy_id=strategy_rec.get("recommended_strategy"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CostCapacityAnalysisResponse(**analysis)


def _advice_response(raw: dict) -> AiInfrastructureAdviceResponse:
    overrides = raw.get("recommended_overrides") or {}
    return AiInfrastructureAdviceResponse(
        summary=raw.get("summary") or "",
        risks=raw.get("risks") or [],
        suggestions=raw.get("suggestions") or [],
        recommended_overrides=RecommendedOverrides(
            machine_type=overrides.get("machine_type"),
            strategy=overrides.get("strategy"),
            machine_type_valid=bool(overrides.get("machine_type_valid")),
            strategy_valid=bool(overrides.get("strategy_valid")),
        ),
        explanation=raw.get("explanation") or "",
        advisor_mode=raw.get("advisor_mode") or "heuristic",
        advisory_only=bool(raw.get("advisory_only", True)),
    )


@router.post(
    "/topologies/{topology_id}/ai-infrastructure-advice",
    response_model=AiInfrastructureAdviceResponse,
)
def post_topology_ai_infrastructure_advice(
    topology_id: UUID,
    body: AiInfrastructureAdviceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AiInfrastructureAdviceResponse:
    topology = _load_topology(db, user, topology_id)
    try:
        raw = advisor_svc.generate_ai_infrastructure_advice(
            topology,
            db=db,
            provider=body.provider,
            selected_strategy=body.selected_strategy,
            selected_machine_type=body.selected_machine_type,
            credential_profile_id=body.credential_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _advice_response(raw)


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
        template_id = strategy_svc.resolve_template_id_for_strategy(strategy_id)
        draft = placement_svc.build_generate_deployment_payload(
            topology,
            db=db,
            provider=body.provider,
            template_id=template_id,
            machine_type=body.machine_type,
            host_count=body.host_count,
            placement_mode=body.placement_mode,
            constraints=placement_persist_svc.constraints_as_dicts(db, topology_id),
            variables=body.variables,
            credentials_ref=body.credentials_ref,
            name=body.name,
        )
        plan = draft["placement_plan"]
        plan_host_count = len(plan.get("hosts") or []) or int(plan.get("recommended_host_count") or 1)
        assert_runtime_strategy_for_generation(strategy_id, host_count=plan_host_count)
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
        saved_plan = placement_persist_svc.save_plan(
            db,
            topology_id=topology.id,
            project_id=topology.project_id,
            actor=user,
            plan=plan,
        )
        deployment.placement_plan_id = saved_plan.id
        placement_summary = draft.get("placement_summary") or {}
        deployment.state_metadata_json = {
            **(deployment.state_metadata_json or {}),
            "topology_placement": plan,
            "placement_summary": placement_summary,
            "topology_capacity": capacity,
            "generated_from_topology": True,
            "deployment_strategy": strategy_id,
            "runtime_strategy": strategy_id,
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
