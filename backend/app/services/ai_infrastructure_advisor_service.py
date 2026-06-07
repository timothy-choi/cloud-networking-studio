"""AI infrastructure advisor — advisory-only planning explanations (Feature 61).

The advisor consumes structured deterministic planner output and produces human-readable
guidance. It never receives credential secrets and cannot trigger infrastructure changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secret_masking import scrub_sensitive_dict
from app.models.topology import Topology
from app.services.deployment_strategy_registry import assert_strategy_available, get_strategy
from app.services.infra_apply_safety import GCP_APPLY_MACHINE_TYPES
from app.services import credential_profile_service as profile_svc
from app.services import cost_capacity_advisor_service as cost_capacity_svc
from app.services import deployment_strategy_recommendation_service as strategy_svc
from app.services import topology_placement_persistence_service as placement_persist_svc
from app.services import topology_placement_planner_service as placement_svc

_log = logging.getLogger(__name__)

_FORBIDDEN_CONTEXT_KEYS = frozenset(
    {
        "encrypted_secret",
        "secret",
        "password",
        "private_key",
        "credentials",
        "credentials_ref",
        "access_key",
        "client_secret",
        "service_account",
    }
)

_APPLY_SAFE_MACHINE_TYPES = sorted(GCP_APPLY_MACHINE_TYPES)
_MACHINE_ORDER = ["e2-micro", "e2-small", "e2-medium"]


AdvisorFn = Callable[[dict[str, Any]], dict[str, Any]]
_advisor_fn: AdvisorFn | None = None


def set_advisor_fn(fn: AdvisorFn | None) -> None:
    """Test hook to inject a mocked advisor backend."""
    global _advisor_fn
    _advisor_fn = fn


def _assert_context_has_no_secrets(context: dict[str, Any]) -> None:
    serialized = json.dumps(context, default=str).lower()
    for token in ("private_key", "encrypted_secret", "-----begin"):
        if token in serialized:
            raise ValueError(f"Advisor context must not contain secret material ({token}).")


def _sanitize_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_metadata(value)
    if isinstance(value, list):
        return [_sanitize_metadata_value(item) for item in value]
    if isinstance(value, str) and "-----BEGIN" in value.upper():
        return "[redacted]"
    return scrub_sensitive_dict({"value": value})["value"]


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        normalized = str(key).lower()
        if (
            normalized in _FORBIDDEN_CONTEXT_KEYS
            or "token" in normalized
            or "secret" in normalized
            or "password" in normalized
            or "private_key" in normalized
            or "credentials" in normalized
        ):
            continue
        sanitized[str(key)] = _sanitize_metadata_value(value)
    return sanitized


def _credential_profile_summary(db: Session, project_id: UUID, profile_id: str | None) -> dict[str, Any] | None:
    if not profile_id:
        return None
    try:
        pid = UUID(str(profile_id))
    except ValueError:
        return None
    profile = profile_svc.get_profile_for_project(db, profile_id=pid, project_id=project_id)
    if profile is None:
        return None
    return {
        "id": str(profile.id),
        "name": profile.name,
        "provider": profile.provider,
        "credential_type": profile.credential_type,
        "project_id": profile.gcp_project_id,
        "validation_status": profile.validation_status,
        "metadata": _sanitize_metadata(profile.metadata_json),
    }


def build_advisor_context(
    topology: Topology,
    *,
    db: Session | None = None,
    provider: str = "gcp",
    selected_strategy: str | None = None,
    selected_machine_type: str | None = None,
    credential_profile_id: str | None = None,
) -> dict[str, Any]:
    machine_type = (selected_machine_type or "").strip() or None
    constraints = []
    if db is not None and hasattr(db, "scalars") and topology.project_id:
        constraints = placement_persist_svc.constraints_as_dicts(db, topology.id)
    plan = placement_svc.build_placement_plan(
        topology,
        provider=provider,
        machine_type=machine_type,
        constraints=constraints,
    )
    strategy = strategy_svc.recommend_strategy_from_plan(plan)
    estimate = placement_svc.build_resource_estimate(topology)
    cost_capacity = cost_capacity_svc.build_cost_capacity_analysis(
        plan,
        provider=provider,
        machine_type=machine_type or plan.get("recommended_machine_type"),
        host_count=plan.get("recommended_host_count"),
    )

    credential_summary = None
    if db is not None and topology.project_id:
        credential_summary = _credential_profile_summary(db, topology.project_id, credential_profile_id)

    nodes_summary = [
        {
            "name": node.name,
            "node_type": str(getattr(node.node_type, "value", node.node_type)),
            "image": node.image,
            "has_resource_metadata": bool(node.config),
        }
        for node in (topology.nodes or [])
    ]

    context = {
        "topology_summary": {
            "id": str(topology.id),
            "name": topology.name,
            "node_count": len(topology.nodes or []),
            "nodes": nodes_summary,
        },
        "resource_estimate": estimate,
        "placement_plan": {
            k: plan[k]
            for k in (
                "total_cpu",
                "total_memory_mb",
                "total_disk_gb",
                "total_replicas",
                "placement_unit_count",
                "recommended_host_count",
                "recommended_machine_type",
                "machine_rationale",
                "hosts",
                "warnings",
                "exposed_ports",
                "suggested_template_id",
                "nodes",
                "placement_mode",
                "constraints_used",
            )
            if k in plan
        },
        "host_recommendation": {
            "recommended_machine_type": plan.get("recommended_machine_type"),
            "recommended_host_count": plan.get("recommended_host_count"),
            "machine_rationale": plan.get("machine_rationale"),
        },
        "strategy_recommendation": {
            "recommended_strategy": strategy.get("recommended_strategy"),
            "alternatives": strategy.get("alternatives"),
            "reasons": strategy.get("reasons"),
            "warnings": strategy.get("warnings"),
            "evaluation": strategy.get("evaluation"),
        },
        "cost_capacity_analysis": cost_capacity,
        "selected": {
            "provider": provider,
            "strategy": selected_strategy or strategy.get("recommended_strategy"),
            "machine_type": machine_type or plan.get("recommended_machine_type"),
            "template_id": selected_strategy or strategy.get("recommended_strategy"),
        },
        "credential_profile": credential_summary,
        "constraints": {
            "apply_safe_machine_types": _APPLY_SAFE_MACHINE_TYPES,
            "max_hosts_apply": 1,
            "placement_constraints": constraints,
        },
    }
    _assert_context_has_no_secrets(context)
    return context


def _pick_suggested_machine_type(context: dict[str, Any]) -> str | None:
    plan = context.get("placement_plan") or {}
    current = str(
        (context.get("selected") or {}).get("machine_type")
        or plan.get("recommended_machine_type")
        or "e2-medium"
    )
    if current not in GCP_APPLY_MACHINE_TYPES:
        current = "e2-medium"

    hosts = plan.get("hosts") or []
    if not hosts:
        return current

    host = hosts[0]
    mem_ratio = int(host.get("memory_used_mb") or 0) / max(1, int(host.get("memory_capacity_mb") or 1))
    cpu_ratio = float(host.get("cpu_used") or 0) / max(0.01, float(host.get("cpu_capacity") or 1))

    warnings_text = " ".join(plan.get("warnings") or []).lower()
    current_idx = _MACHINE_ORDER.index(current) if current in _MACHINE_ORDER else len(_MACHINE_ORDER) - 1

    if "exceed memory" in warnings_text or mem_ratio > 0.85:
        next_idx = min(current_idx + 1, len(_MACHINE_ORDER) - 1)
        return _MACHINE_ORDER[next_idx]

    if mem_ratio < 0.35 and cpu_ratio < 0.35 and current_idx > 0:
        return _MACHINE_ORDER[current_idx - 1]

    return current


def validate_recommended_overrides(
    context: dict[str, Any],
    *,
    topology: Topology,
    provider: str = "gcp",
) -> dict[str, Any]:
    suggested_machine = _pick_suggested_machine_type(context)
    strategy_id = str(
        (context.get("strategy_recommendation") or {}).get("recommended_strategy") or "docker-vm"
    )

    machine_valid = bool(suggested_machine and suggested_machine in GCP_APPLY_MACHINE_TYPES)
    strategy_valid = False
    if get_strategy(strategy_id) is not None:
        try:
            assert_strategy_available(strategy_id)
            strategy_valid = True
        except ValueError:
            strategy_valid = False

    if machine_valid and suggested_machine:
        try:
            replan = placement_svc.build_placement_plan(
                topology,
                provider=provider,
                machine_type=suggested_machine,
            )
            warning_text = " ".join(replan.get("warnings") or [])
            if any(
                phrase in warning_text
                for phrase in (
                    "Insufficient capacity",
                    "exceed memory capacity",
                    "exceed CPU capacity",
                    "CPU demand exceeds",
                )
            ):
                machine_valid = False
        except ValueError:
            machine_valid = False

    return {
        "machine_type": suggested_machine,
        "strategy": strategy_id if strategy_valid else "docker-vm",
        "machine_type_valid": machine_valid,
        "strategy_valid": strategy_valid,
    }


def _heuristic_advisor(context: dict[str, Any]) -> dict[str, Any]:
    topo = context.get("topology_summary") or {}
    plan = context.get("placement_plan") or {}
    strategy = context.get("strategy_recommendation") or {}
    selected = context.get("selected") or {}

    host_count = int(plan.get("recommended_host_count") or len(plan.get("hosts") or []))
    machine = selected.get("machine_type") or plan.get("recommended_machine_type") or "e2-medium"
    strategy_id = selected.get("strategy") or strategy.get("recommended_strategy") or "docker-vm"
    workload_nodes = len(plan.get("nodes") or [])
    replicas = int(plan.get("total_replicas") or plan.get("placement_unit_count") or 0)

    risks: list[str] = []
    suggestions: list[str] = []

    for warning in plan.get("warnings") or []:
        risks.append(warning)
    for warning in strategy.get("warnings") or []:
        if warning not in risks:
            risks.append(warning)

    evaluation = strategy.get("evaluation") or {}
    if evaluation.get("stateful_workloads"):
        risks.append("Stateful workloads may need persistent volumes not provisioned by docker-vm.")
    if evaluation.get("public_exposure"):
        risks.append("Public exposure requires firewall rules and careful CIDR restrictions.")

    hosts = plan.get("hosts") or []
    if hosts:
        host = hosts[0]
        mem_pct = int(100 * int(host.get("memory_used_mb") or 0) / max(1, int(host.get("memory_capacity_mb") or 1)))
        cpu_pct = int(100 * float(host.get("cpu_used") or 0) / max(0.01, float(host.get("cpu_capacity") or 1)))
        suggestions.append(f"[Efficiency] Host utilization is about {cpu_pct}% CPU and {mem_pct}% memory.")
        if mem_pct > 80:
            suggestions.append("[Scaling] Memory utilization is high — consider a larger machine type.")
        elif mem_pct < 40 and cpu_pct < 40:
            suggestions.append("[Cost] Utilization is low — a smaller machine type may reduce cost.")

    if host_count > 1:
        suggestions.append(
            "[Scaling] Placement spans multiple hosts; docker-multi-vm is planned but not yet apply-ready."
        )
    if replicas >= 5:
        suggestions.append(
            "[Scaling] High replica count may benefit from orchestration (k8s-cluster is future work)."
        )

    suggestions.append("[Security] Restrict allowed_ssh_cidr and allowed_app_cidr — avoid 0.0.0.0/0 in production.")
    suggestions.append("[Networking] Exposed ports require matching firewall rules on the VM.")

    summary = (
        f"Topology '{topo.get('name')}' has {workload_nodes} workload node(s) "
        f"({replicas} placement unit(s)). The deterministic planner recommends "
        f"{machine} on {host_count} host(s) using strategy '{strategy_id}'."
    )

    explanation = (
        "The planner measured CPU, memory, and disk from your node metadata, bin-packed replicas onto "
        "virtual hosts, and picked a deployment strategy. This advisor explains those results in plain "
        "language. Suggestions are advisory — you choose overrides, and the backend still validates "
        "every deployment before Terraform runs."
    )

    return {
        "summary": summary,
        "risks": risks,
        "suggestions": suggestions,
        "explanation": explanation,
    }


def _llm_advisor(context: dict[str, Any]) -> dict[str, Any]:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return _heuristic_advisor(context)

    try:
        import httpx
    except ImportError:
        _log.warning("httpx not available; falling back to heuristic advisor")
        return _heuristic_advisor(context)

    prompt = (
        "You are an infrastructure planning advisor for a generic Docker workload platform. "
        "Analyze the JSON planner context and respond with ONLY valid JSON matching this schema:\n"
        '{"summary": str, "risks": [str], "suggestions": [str], "explanation": str}\n'
        "Do not recommend executing Terraform. Do not ask for secrets. Be concise.\n\n"
        f"Context:\n{json.dumps(context, default=str)}"
    )
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": "Respond with JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return {
            "summary": str(parsed.get("summary") or ""),
            "risks": [str(r) for r in parsed.get("risks") or []],
            "suggestions": [str(s) for s in parsed.get("suggestions") or []],
            "explanation": str(parsed.get("explanation") or ""),
        }
    except Exception as exc:
        _log.warning("LLM advisor failed (%s); using heuristic fallback", exc)
        return _heuristic_advisor(context)


def _resolve_advisor() -> tuple[AdvisorFn, str]:
    if _advisor_fn is not None:
        return _advisor_fn, "mock"
    provider = (settings.ai_advisor_provider or "heuristic").strip().lower()
    if provider == "openai":
        return _llm_advisor, "openai"
    return _heuristic_advisor, "heuristic"


def generate_ai_infrastructure_advice(
    topology: Topology,
    *,
    db: Session | None = None,
    provider: str = "gcp",
    selected_strategy: str | None = None,
    selected_machine_type: str | None = None,
    credential_profile_id: str | None = None,
) -> dict[str, Any]:
    context = build_advisor_context(
        topology,
        db=db,
        provider=provider,
        selected_strategy=selected_strategy,
        selected_machine_type=selected_machine_type,
        credential_profile_id=credential_profile_id,
    )
    advisor_fn, mode = _resolve_advisor()
    advice = advisor_fn(context)
    overrides = validate_recommended_overrides(context, topology=topology, provider=provider)

    return {
        "summary": advice.get("summary") or "",
        "risks": advice.get("risks") or [],
        "suggestions": advice.get("suggestions") or [],
        "recommended_overrides": overrides,
        "explanation": advice.get("explanation") or "",
        "advisor_mode": mode,
        "advisory_only": True,
    }
