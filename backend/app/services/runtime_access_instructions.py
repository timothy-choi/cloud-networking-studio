"""Human-oriented integration snippets (local dev, CI, Kubernetes, API)."""

from __future__ import annotations

from typing import Any

from app.models.deployment import Deployment, DeploymentStatus
from app.models.topology import Topology


def build_runtime_instructions(
    *,
    deployment: Deployment,
    topology: Topology,
    resources: list[dict[str, Any]],
    exposures: list[dict[str, Any]] | None = None,
    api_base: str = "/api",
) -> dict[str, Any]:
    """Return structured guidance keyed by integration mode."""
    exposures = exposures or []
    dep_id = str(deployment.id)
    topo_id = str(topology.id)
    ns_or_net = next(
        (r.get("namespace_or_network") for r in resources if r.get("namespace_or_network")),
        None,
    )
    first_svc = next((r for r in resources if r.get("type") == "service"), None)
    internal = (first_svc or {}).get("internal_url") if first_svc else None

    k8s_ns = ns_or_net if deployment.runtime_target != "docker" else None
    svc_name = (first_svc or {}).get("runtime_name") if first_svc else None

    if k8s_ns and svc_name:
        pf_lines = [
            f"kubectl port-forward -n {k8s_ns} svc/{svc_name} 8080:80",
            "curl -sS http://127.0.0.1:8080/",
        ]
    else:
        pf_lines = [
            "# Docker: reach workloads from another container on the same user-defined bridge,",
            "# or use docker exec inside the node container.",
            f"# Example network/container names are listed under runtime resources for deployment {dep_id}.",
        ]

    active_ex = [e for e in exposures if e.get("status") == "active"]
    curl_lines: list[str] = []
    exposed_items: list[dict[str, Any]] = []
    for e in active_ex:
        url = e.get("external_url")
        meta = e.get("metadata") or {}
        rid = e.get("runtime_resource_id")
        if url:
            curl_lines.append(f"curl -sS {url}")
            exposed_items.append(
                {
                    "runtime_resource_id": rid,
                    "external_url": url,
                    "exposure_type": e.get("exposure_type"),
                    "curl": f"curl -sS {url}",
                }
            )
        else:
            cmds = meta.get("commands") if isinstance(meta.get("commands"), list) else []
            exposed_items.append(
                {
                    "runtime_resource_id": rid,
                    "exposure_type": e.get("exposure_type"),
                    "manual": bool(meta.get("manual_port_forward_required")),
                    "commands": cmds,
                }
            )
    if curl_lines:
        pf_lines = list(pf_lines) + ["# Exposed services (HTTP):"] + curl_lines

    env_hint: dict[str, str] = {}
    if internal:
        env_hint["CNS_SERVICE_URL"] = internal
    else:
        env_hint = {"CNS_TOPOLOGY_ID": topo_id, "CNS_DEPLOYMENT_ID": dep_id}

    out: dict[str, Any] = {
        "local_dev": {
            "title": "Connect from local machine",
            "commands": pf_lines,
        },
        "app_env": {
            "title": "Use from app",
            "env": env_hint,
        },
        "ci_cd": {
            "title": "Use in CI/CD",
            "commands": [
                f"curl -sS -X POST {api_base}/topologies/{topo_id}/deploy \\",
                '  -H "Authorization: Bearer $CNS_TOKEN"',
                f"pytest tests/integration --topology {topo_id}",
                f"curl -sS -X POST {api_base}/deployments/{dep_id}/destroy \\",
                '  -H "Authorization: Bearer $CNS_TOKEN"',
            ],
        },
        "kubernetes": {
            "title": "Use from Kubernetes workload",
            "notes": (
                "Call cluster DNS from pods in the same cluster, or mount a kubeconfig "
                "with RBAC scoped to this namespace."
            ),
            "config_map": {
                "labels": {
                    "app": "cloud-networking-studio",
                    "topology_id": topo_id,
                    "deployment_id": dep_id,
                    **(
                        {"project_id": str(topology.project_id)}
                        if topology.project_id
                        else {}
                    ),
                },
                "example_dns": internal,
            },
        },
        "api": {
            "title": "Control through API",
            "endpoints": [
                {
                    "method": "GET",
                    "path": f"{api_base}/deployments/{dep_id}/runtime",
                    "description": "Live snapshot + persisted access rows",
                },
                {
                    "method": "GET",
                    "path": f"{api_base}/deployments/{dep_id}/runtime/instructions",
                    "description": "Integration snippets only",
                },
                {
                    "method": "GET",
                    "path": f"{api_base}/deployments/{dep_id}/runtime/exposures",
                    "description": "List service exposure records",
                },
                {
                    "method": "POST",
                    "path": f"{api_base}/deployments/{dep_id}/runtime/services/{{runtime_service_resource_id}}/expose",
                    "description": "Create/update external reachability metadata for one service row",
                },
                {
                    "method": "DELETE",
                    "path": f"{api_base}/deployments/{dep_id}/runtime/services/{{runtime_service_resource_id}}/expose",
                    "description": "Mark exposure as removed",
                },
                {
                    "method": "GET",
                    "path": f"{api_base}/topologies/{topo_id}/runtime",
                    "description": "Topology-wide runtime view",
                },
            ],
        },
    }
    if exposed_items:
        out["exposed_services"] = {
            "title": "Exposed services",
            "items": exposed_items,
        }
    return out


def deployment_access_status_label(dep: Deployment) -> str:
    if dep.status == DeploymentStatus.SUCCEEDED:
        return "running"
    if dep.status == DeploymentStatus.DEPLOYING:
        return "pending"
    if dep.status == DeploymentStatus.FAILED:
        return "failed"
    if dep.status == DeploymentStatus.STOPPED:
        return "destroyed"
    return dep.status.value
