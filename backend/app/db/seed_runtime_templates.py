"""Idempotent starter runtime templates (Step 43)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runtime_template import RuntimeTemplate, TemplateVisibility


def _snap(
    *,
    topo_name: str,
    topo_desc: str,
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "topology": {
            "name": topo_name,
            "description": topo_desc,
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "config": None,
        },
        "nodes": nodes,
        "links": links,
    }


STARTER_SPECS: list[dict[str, Any]] = [
    {
        "slug": "client-service",
        "name": "Client + service",
        "description": "Two workloads on a shared segment — typical client/server lab.",
        "category": "starter",
        "tags": ["docker", "microservice", "demo"],
        "snapshot": _snap(
            topo_name="client-service",
            topo_desc="Client workload talks to a backend service over a lab network.",
            nodes=[
                {
                    "id": "cs-client",
                    "name": "client",
                    "node_type": "generic",
                    "image": "alpine:3.19",
                    "ip_address": None,
                    "config": None,
                },
                {
                    "id": "cs-service",
                    "name": "server",
                    "node_type": "generic",
                    "image": "nginx:alpine",
                    "ip_address": None,
                    "config": None,
                },
            ],
            links=[
                {
                    "source_id": "cs-client",
                    "target_id": "cs-service",
                    "network_name": "app-net",
                    "cidr": "10.50.0.0/24",
                    "gateway": None,
                    "vlan_tag": None,
                    "source_endpoint_ip": None,
                    "target_endpoint_ip": None,
                    "config": None,
                },
            ],
        ),
    },
    {
        "slug": "gateway-api-db",
        "name": "Gateway, API, and database",
        "description": "Three-tier style topology for edge routing, app logic, and persistence.",
        "category": "starter",
        "tags": ["kubernetes", "tiered", "demo"],
        "snapshot": _snap(
            topo_name="gateway-api-db",
            topo_desc="Gateway fronts an API tier backed by a database node (intent only).",
            nodes=[
                {
                    "id": "gw",
                    "name": "gateway",
                    "node_type": "gateway",
                    "image": None,
                    "ip_address": None,
                    "config": None,
                },
                {
                    "id": "api",
                    "name": "api",
                    "node_type": "generic",
                    "image": None,
                    "ip_address": None,
                    "config": None,
                },
                {
                    "id": "db",
                    "name": "database",
                    "node_type": "generic",
                    "image": None,
                    "ip_address": None,
                    "config": None,
                },
            ],
            links=[
                {
                    "source_id": "gw",
                    "target_id": "api",
                    "network_name": "edge",
                    "cidr": "10.60.0.0/24",
                    "gateway": None,
                    "vlan_tag": None,
                    "source_endpoint_ip": None,
                    "target_endpoint_ip": None,
                    "config": None,
                },
                {
                    "source_id": "api",
                    "target_id": "db",
                    "network_name": "data",
                    "cidr": "10.61.0.0/24",
                    "gateway": None,
                    "vlan_tag": None,
                    "source_endpoint_ip": None,
                    "target_endpoint_ip": None,
                    "config": None,
                },
            ],
        ),
    },
    {
        "slug": "failure-injection-lab",
        "name": "Failure injection lab",
        "description": "Minimal pair of nodes for stop/restart/kill drills and drift experiments.",
        "category": "starter",
        "tags": ["resilience", "chaos", "demo"],
        "snapshot": _snap(
            topo_name="failure-injection-lab",
            topo_desc="Two connected nodes suitable for failure injections and traffic tests.",
            nodes=[
                {
                    "id": "fi-a",
                    "name": "node-a",
                    "node_type": "generic",
                    "image": None,
                    "ip_address": None,
                    "config": None,
                },
                {
                    "id": "fi-b",
                    "name": "node-b",
                    "node_type": "generic",
                    "image": None,
                    "ip_address": None,
                    "config": None,
                },
            ],
            links=[
                {
                    "source_id": "fi-a",
                    "target_id": "fi-b",
                    "network_name": "lab",
                    "cidr": "10.70.0.0/24",
                    "gateway": None,
                    "vlan_tag": None,
                    "source_endpoint_ip": None,
                    "target_endpoint_ip": None,
                    "config": None,
                },
            ],
        ),
    },
]


def ensure_starter_runtime_templates(db: Session) -> None:
    """Insert built-in catalog templates once (matched by unique ``slug``)."""
    for spec in STARTER_SPECS:
        slug = spec["slug"]
        exists = db.scalar(select(RuntimeTemplate.id).where(RuntimeTemplate.slug == slug))
        if exists is not None:
            continue
        db.add(
            RuntimeTemplate(
                name=spec["name"],
                description=spec["description"],
                category=spec["category"],
                tags=list(spec["tags"]),
                owner_user_id=None,
                project_id=None,
                visibility=TemplateVisibility.PROJECT.value,
                topology_snapshot=spec["snapshot"],
                source_topology_id=None,
                slug=slug,
            )
        )
    db.commit()
    _refresh_client_service_catalog_snapshot(db)


def _refresh_client_service_catalog_snapshot(db: Session) -> None:
    """Apply latest ``client-service`` graph to existing catalog rows (idempotent)."""
    spec = next((s for s in STARTER_SPECS if s["slug"] == "client-service"), None)
    if spec is None:
        return
    row = db.scalar(select(RuntimeTemplate).where(RuntimeTemplate.slug == "client-service"))
    if row is None:
        return
    row.topology_snapshot = spec["snapshot"]
    db.commit()
