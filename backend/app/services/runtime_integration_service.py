"""Step 49: integration snippets and topology→runtime mapping."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.models.topology import Topology, TopologyNode
from app.schemas.runtime_integration import (
    DeploymentIntegrationResponse,
    DeploymentRuntimeMappingResponse,
    IntegrationSnippet,
    RuntimeMappingRow,
)
from app.services.deployment_runtime_resource_service import (
    list_runtime_resources,
    resource_row_to_public_dict,
)
from app.services.deployment_service_exposure_service import (
    exposure_to_api_dict,
    list_exposure_rows,
)
from app.services.runtime_access_instructions import build_runtime_instructions
from app.services.runtime_state_service import build_deployment_runtime


def _snippet(sid: str, title: str, language: str, content: str) -> IntegrationSnippet:
    return IntegrationSnippet(id=sid, title=title, language=language, content=content)


def build_integration_snippets(
    *,
    deployment: Deployment,
    topology: Topology,
    resources: list[dict[str, Any]],
    exposures: list[dict[str, Any]],
    api_base: str = "/api",
) -> list[IntegrationSnippet]:
    dep_id = str(deployment.id)
    topo_id = str(topology.id)
    prov = (deployment.runtime_target or "docker").strip().lower()
    snippets: list[IntegrationSnippet] = []

    for r in resources:
        if r.get("type") != "service":
            continue
        internal = r.get("internal_url")
        runtime_name = r.get("runtime_name") or r.get("name") or "workload"
        ns = r.get("namespace_or_network") or ""
        meta = r.get("metadata") or {}
        if internal:
            snippets.append(
                _snippet(
                    f"curl-{r.get('name', runtime_name)}",
                    f"curl — {r.get('name', runtime_name)}",
                    "bash",
                    f"curl -sS {internal}",
                )
            )
            snippets.append(
                _snippet(
                    f"python-{r.get('name', runtime_name)}",
                    f"Python requests — {r.get('name', runtime_name)}",
                    "python",
                    (
                        "import requests\n"
                        f"r = requests.get({internal!r}, timeout=10)\n"
                        "r.raise_for_status()\n"
                        "print(r.text)"
                    ),
                )
            )
            snippets.append(
                _snippet(
                    f"node-{r.get('name', runtime_name)}",
                    f"Node fetch — {r.get('name', runtime_name)}",
                    "javascript",
                    (
                        f"const res = await fetch({internal!r});\n"
                        "if (!res.ok) throw new Error(await res.text());\n"
                        "console.log(await res.text());"
                    ),
                )
            )
        if prov == "docker" and runtime_name:
            snippets.append(
                _snippet(
                    f"docker-exec-{r.get('name', runtime_name)}",
                    f"docker exec — {r.get('name', runtime_name)}",
                    "bash",
                    f"docker exec -it {runtime_name} /bin/sh",
                )
            )
            if ns:
                snippets.append(
                    _snippet(
                        f"docker-net-{r.get('name', runtime_name)}",
                        f"Docker network — {ns}",
                        "bash",
                        f"docker network inspect {ns}",
                    )
                )
        if prov == "kubernetes" and ns and runtime_name:
            pod = meta.get("deployment") or meta.get("pod") or runtime_name
            snippets.append(
                _snippet(
                    f"kubectl-get-{r.get('name', runtime_name)}",
                    f"kubectl get pods — {ns}",
                    "bash",
                    f"kubectl get pods -n {ns} -l deployment_id={dep_id}",
                )
            )
            snippets.append(
                _snippet(
                    f"kubectl-exec-{r.get('name', runtime_name)}",
                    f"kubectl exec — {pod}",
                    "bash",
                    f"kubectl exec -n {ns} -it deploy/{pod} -- /bin/sh",
                )
            )
            svc = meta.get("service") or runtime_name
            snippets.append(
                _snippet(
                    f"kubectl-pf-{r.get('name', runtime_name)}",
                    f"kubectl port-forward — {svc}",
                    "bash",
                    f"kubectl port-forward -n {ns} svc/{svc} 8080:80",
                )
            )

    snippets.append(
        _snippet(
            "github-actions-deploy",
            "GitHub Actions — deploy topology",
            "yaml",
            (
                "name: cns-deploy\n"
                "on: [workflow_dispatch]\n"
                "jobs:\n"
                "  deploy:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: |\n"
                f"          curl -sS -X POST ${{{{ env.CNS_API }}}}{api_base}/topologies/{topo_id}/deploy \\\n"
                '            -H "Authorization: Bearer ${{ secrets.CNS_TOKEN }}"'
            ),
        )
    )
    return snippets


def build_deployment_integration(
    session: Session, deployment_id: UUID, *, api_base: str = "/api"
) -> DeploymentIntegrationResponse:
    snap = build_deployment_runtime(session, deployment_id)
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")

    resources = [resource_row_to_public_dict(r) for r in list_runtime_resources(session, deployment_id)]
    exposures = [exposure_to_api_dict(e) for e in list_exposure_rows(session, deployment_id)]
    instructions = build_runtime_instructions(
        deployment=dep,
        topology=topo,
        resources=resources,
        exposures=exposures,
        api_base=api_base,
    )
    snippets = build_integration_snippets(
        deployment=dep,
        topology=topo,
        resources=resources,
        exposures=exposures,
        api_base=api_base,
    )

    internal_eps = [
        {
            "name": r.get("name"),
            "type": r.get("type"),
            "internal_url": r.get("internal_url"),
            "runtime_name": r.get("runtime_name"),
            "namespace_or_network": r.get("namespace_or_network"),
        }
        for r in resources
        if r.get("internal_url")
    ]
    exposed_eps = [
        {
            "runtime_resource_id": e.get("runtime_resource_id"),
            "external_url": e.get("external_url"),
            "exposure_type": e.get("exposure_type"),
            "status": e.get("status"),
        }
        for e in exposures
        if e.get("status") == "active"
    ]

    env_vars: dict[str, str] = {}
    app_env = instructions.get("app_env") if isinstance(instructions.get("app_env"), dict) else {}
    if isinstance(app_env.get("env"), dict):
        env_vars.update({str(k): str(v) for k, v in app_env["env"].items()})
    env_vars.setdefault("CNS_DEPLOYMENT_ID", str(dep.id))
    env_vars.setdefault("CNS_TOPOLOGY_ID", str(topo.id))

    connect = {
        "title": "Connect your app",
        "local": instructions.get("local_dev"),
        "env": env_vars,
        "service_urls": [e["internal_url"] for e in internal_eps if e.get("internal_url")],
        "exposed_urls": [e["external_url"] for e in exposed_eps if e.get("external_url")],
        "ci_cd": instructions.get("ci_cd"),
    }

    return DeploymentIntegrationResponse(
        deployment_id=dep.id,
        topology_id=topo.id,
        runtime_provider=snap.runtime_provider,
        namespace_or_network=snap.namespace_or_network,
        internal_endpoints=internal_eps,
        exposed_endpoints=exposed_eps,
        env_vars=env_vars,
        connect_your_app=connect,
        snippets=snippets,
        instructions=instructions,
    )


def build_deployment_runtime_mapping(
    session: Session, deployment_id: UUID
) -> DeploymentRuntimeMappingResponse:
    dep = session.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = session.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")

    snap = build_deployment_runtime(session, deployment_id)
    nodes_by_id = {
        n.id: n
        for n in session.scalars(
            select(TopologyNode).where(TopologyNode.topology_id == dep.topology_id)
        ).all()
    }
    containers_by_node: dict[str, Any] = {}
    for c in snap.containers:
        if c.node_id is not None:
            containers_by_node[str(c.node_id)] = c

    rows: list[RuntimeMappingRow] = []
    seen_nodes: set[UUID] = set()
    for r in list_runtime_resources(session, deployment_id):
        pub = resource_row_to_public_dict(r)
        if pub.get("type") not in ("node", "service"):
            continue
        nid_raw = pub.get("node_id") or pub.get("service_id")
        if not nid_raw:
            continue
        try:
            nid = UUID(str(nid_raw))
        except ValueError:
            continue
        if pub.get("type") == "service" and nid in seen_nodes:
            continue
        if pub.get("type") == "node":
            seen_nodes.add(nid)
        topo_node = nodes_by_id.get(nid)
        ctr = containers_by_node.get(str(nid))
        meta = pub.get("metadata") or {}
        rows.append(
            RuntimeMappingRow(
                topology_node_id=nid,
                topology_node_name=topo_node.name if topo_node else pub.get("name"),
                resource_id=r.id,
                resource_type=pub.get("type"),
                runtime_name=pub.get("runtime_name"),
                container_id=ctr.container_id if ctr else meta.get("container_id"),
                pod_name=meta.get("deployment") or meta.get("pod"),
                internal_url=pub.get("internal_url"),
                external_url=pub.get("external_url"),
                namespace_or_network=pub.get("namespace_or_network"),
                status=pub.get("status"),
            )
        )

    for nid, topo_node in nodes_by_id.items():
        if nid in seen_nodes:
            continue
        ctr = containers_by_node.get(str(nid))
        if ctr is None:
            continue
        rows.append(
            RuntimeMappingRow(
                topology_node_id=nid,
                topology_node_name=topo_node.name,
                resource_type="container",
                runtime_name=ctr.name,
                container_id=ctr.container_id,
                internal_url=None,
                namespace_or_network=None,
                status=ctr.status,
            )
        )

    return DeploymentRuntimeMappingResponse(
        deployment_id=dep.id,
        topology_id=topo.id,
        runtime_provider=dep.runtime_target or "docker",
        rows=rows,
    )
