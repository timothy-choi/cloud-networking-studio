"""Build topology snapshots, versions, and rollback (Step 56)."""

from __future__ import annotations

import copy
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.secret_masking import scrub_sensitive_dict
from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.models.topology_version import TopologyVersion
from app.models.user import User
from app.services.audit_service import record_audit


def build_topology_snapshot(topology: Topology) -> dict[str, Any]:
    """Serialize topology graph + metadata for immutable version storage."""
    return {
        "topology": {
            "name": topology.name,
            "description": topology.description,
            "status": topology.status.value if isinstance(topology.status, TopologyStatus) else topology.status,
            "runtime_target": topology.runtime_target,
            "networking_mode": topology.networking_mode,
            "config": copy.deepcopy(topology.config) if topology.config else None,
        },
        "nodes": [
            {
                "id": str(n.id),
                "name": n.name,
                "node_type": n.node_type.value if isinstance(n.node_type, NodeType) else n.node_type,
                "image": n.image,
                "ip_address": n.ip_address,
                "config": copy.deepcopy(n.config) if n.config else None,
            }
            for n in sorted(topology.nodes, key=lambda x: x.name)
        ],
        "links": [
            {
                "id": str(lnk.id),
                "source_node_id": str(lnk.source_node_id),
                "target_node_id": str(lnk.target_node_id),
                "network_name": lnk.network_name,
                "cidr": lnk.cidr,
                "gateway": lnk.gateway,
                "vlan_tag": lnk.vlan_tag,
                "source_endpoint_ip": lnk.source_endpoint_ip,
                "target_endpoint_ip": lnk.target_endpoint_ip,
                "config": copy.deepcopy(lnk.config) if lnk.config else None,
            }
            for lnk in topology.links
        ],
    }


def _next_version_number(db: Session, topology_id: UUID) -> int:
    current = db.scalar(
        select(func.max(TopologyVersion.version_number)).where(
            TopologyVersion.topology_id == topology_id
        )
    )
    return int(current or 0) + 1


def create_topology_version(
    db: Session,
    *,
    topology: Topology,
    created_by: User | None,
    source: str,
    name: str | None = None,
    description: str | None = None,
    parent_version_id: UUID | None = None,
    snapshot: dict[str, Any] | None = None,
) -> TopologyVersion:
    snap = snapshot if snapshot is not None else build_topology_snapshot(topology)
    version = TopologyVersion(
        topology_id=topology.id,
        version_number=_next_version_number(db, topology.id),
        name=name,
        description=description,
        snapshot_json=snap,
        created_by_user_id=created_by.id if created_by else None,
        source=source,
        parent_version_id=parent_version_id,
    )
    db.add(version)
    db.flush()
    return version


def autosave_enabled(topology: Topology) -> bool:
    cfg = topology.config or {}
    if cfg.get("autosave_versions") is True:
        return True
    return getattr(settings, "topology_autosave_versions", False)


def maybe_autosave_version(db: Session, topology: Topology, user: User | None) -> TopologyVersion | None:
    if not autosave_enabled(topology):
        return None
    version = create_topology_version(
        db,
        topology=topology,
        created_by=user,
        source="autosave",
        name=f"Autosave v{_next_version_number(db, topology.id)}",
    )
    record_audit(
        db,
        action="topology.version.created",
        resource_type="topology_version",
        resource_id=version.id,
        project_id=topology.project_id,
        actor_user_id=user.id if user else None,
        status="success",
        metadata=scrub_sensitive_dict(
            {
                "topology_id": str(topology.id),
                "version_number": version.version_number,
                "source": "autosave",
            }
        ),
    )
    return version


def get_version_for_topology(
    db: Session, topology_id: UUID, version_id: UUID
) -> TopologyVersion | None:
    return db.scalar(
        select(TopologyVersion).where(
            TopologyVersion.id == version_id,
            TopologyVersion.topology_id == topology_id,
        )
    )


def list_versions(db: Session, topology_id: UUID) -> list[TopologyVersion]:
    return list(
        db.scalars(
            select(TopologyVersion)
            .where(TopologyVersion.topology_id == topology_id)
            .order_by(TopologyVersion.version_number.desc())
        ).all()
    )


def apply_snapshot_to_topology(db: Session, topology: Topology, snapshot: dict[str, Any]) -> None:
    """Restore topology ORM state from a version snapshot (mutates topology only)."""
    topo_meta = snapshot.get("topology") or {}
    topology.name = topo_meta.get("name") or topology.name
    topology.description = topo_meta.get("description")
    status_raw = topo_meta.get("status")
    if status_raw:
        topology.status = TopologyStatus(status_raw)
    if topo_meta.get("runtime_target"):
        topology.runtime_target = topo_meta["runtime_target"]
    if topo_meta.get("networking_mode"):
        topology.networking_mode = topo_meta["networking_mode"]
    topology.config = copy.deepcopy(topo_meta.get("config"))

    db.execute(delete(TopologyLink).where(TopologyLink.topology_id == topology.id))
    db.execute(delete(TopologyNode).where(TopologyNode.topology_id == topology.id))
    db.flush()

    node_id_map: dict[str, uuid.UUID] = {}
    for raw in snapshot.get("nodes") or []:
        node_id = uuid.UUID(raw["id"])
        node_id_map[raw["id"]] = node_id
        db.add(
            TopologyNode(
                id=node_id,
                topology_id=topology.id,
                name=raw["name"],
                node_type=NodeType(raw["node_type"]),
                image=raw.get("image"),
                ip_address=raw.get("ip_address"),
                config=copy.deepcopy(raw.get("config")),
            )
        )
    db.flush()

    for raw in snapshot.get("links") or []:
        db.add(
            TopologyLink(
                id=uuid.UUID(raw["id"]),
                topology_id=topology.id,
                source_node_id=node_id_map.get(raw["source_node_id"], uuid.UUID(raw["source_node_id"])),
                target_node_id=node_id_map.get(raw["target_node_id"], uuid.UUID(raw["target_node_id"])),
                network_name=raw["network_name"],
                cidr=raw.get("cidr"),
                gateway=raw.get("gateway"),
                vlan_tag=raw.get("vlan_tag"),
                source_endpoint_ip=raw.get("source_endpoint_ip"),
                target_endpoint_ip=raw.get("target_endpoint_ip"),
                config=copy.deepcopy(raw.get("config")),
            )
        )
    db.flush()


def rollback_topology_to_version(
    db: Session,
    *,
    topology: Topology,
    version: TopologyVersion,
    actor: User,
) -> TopologyVersion:
    """Restore topology from snapshot and record a new rollback version."""
    snapshot = copy.deepcopy(version.snapshot_json)
    apply_snapshot_to_topology(db, topology, snapshot)
    db.refresh(topology, attribute_names=["nodes", "links"])

    rollback_version = create_topology_version(
        db,
        topology=topology,
        created_by=actor,
        source="rollback",
        name=f"Rollback to v{version.version_number}",
        description=f"Restored from version {version.version_number}",
        parent_version_id=version.id,
        snapshot=build_topology_snapshot(topology),
    )
    return rollback_version


def load_topology_with_graph(db: Session, topology_id: UUID) -> Topology | None:
    return db.scalar(
        select(Topology)
        .where(Topology.id == topology_id)
        .options(selectinload(Topology.nodes), selectinload(Topology.links))
    )
