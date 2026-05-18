"""Runtime template CRUD, visibility, and clone-to-topology (Step 43)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.project_membership import ProjectMembership
from app.models.runtime_template import RuntimeTemplate, TemplateVisibility
from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.models.user import User
from app.schemas.template import (
    RuntimeTemplateDetailResponse,
    RuntimeTemplateResponse,
    TemplateCloneRequest,
    TemplateFromTopologyCreate,
)
from app.services.access_control import (
    default_project_for_user,
    get_project_membership_role,
    require_project_editor,
    require_topology_editor,
)

SNAPSHOT_VERSION = 1


def _node_type_value(nt: Any) -> str:
    if isinstance(nt, NodeType):
        return nt.value
    return str(nt)


def build_topology_snapshot(topo: Topology) -> dict[str, Any]:
    """Serialize topology graph for ``topology_snapshot`` JSON."""
    nodes_out: list[dict[str, Any]] = []
    for n in topo.nodes:
        nodes_out.append(
            {
                "id": str(n.id),
                "name": n.name,
                "node_type": _node_type_value(n.node_type),
                "image": n.image,
                "ip_address": n.ip_address,
                "config": n.config,
            }
        )
    links_out: list[dict[str, Any]] = []
    for ln in topo.links:
        links_out.append(
            {
                "source_id": str(ln.source_node_id),
                "target_id": str(ln.target_node_id),
                "network_name": ln.network_name,
                "cidr": ln.cidr,
                "gateway": ln.gateway,
                "vlan_tag": ln.vlan_tag,
                "source_endpoint_ip": ln.source_endpoint_ip,
                "target_endpoint_ip": ln.target_endpoint_ip,
                "config": ln.config,
            }
        )
    return {
        "version": SNAPSHOT_VERSION,
        "topology": {
            "name": topo.name,
            "description": topo.description,
            "runtime_target": topo.runtime_target,
            "networking_mode": topo.networking_mode,
            "config": topo.config,
        },
        "nodes": nodes_out,
        "links": links_out,
    }


def _template_readable_predicate(user_id: UUID):
    member_projects = select(ProjectMembership.project_id).where(ProjectMembership.user_id == user_id)
    return or_(
        RuntimeTemplate.slug.is_not(None),
        and_(
            RuntimeTemplate.visibility == TemplateVisibility.PRIVATE.value,
            RuntimeTemplate.owner_user_id == user_id,
        ),
        and_(
            RuntimeTemplate.visibility == TemplateVisibility.PROJECT.value,
            RuntimeTemplate.project_id.in_(member_projects),
        ),
    )


def _can_delete_template(db: Session, user: User, row: RuntimeTemplate) -> bool:
    if row.slug is not None:
        return False
    if row.owner_user_id == user.id:
        return True
    if row.project_id is None:
        return False
    role = get_project_membership_role(db, user, row.project_id)
    return role == "owner"


def template_to_response(row: RuntimeTemplate, *, user: User, db: Session) -> RuntimeTemplateResponse:
    tags = row.tags if isinstance(row.tags, list) else []
    tags_s = [str(t) for t in tags][:50]
    return RuntimeTemplateResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        category=row.category or "general",
        tags=tags_s,
        owner_user_id=row.owner_user_id,
        project_id=row.project_id,
        visibility=row.visibility,
        source_topology_id=row.source_topology_id,
        slug=row.slug,
        created_at=row.created_at,
        updated_at=row.updated_at,
        can_delete=_can_delete_template(db, user, row),
    )


def template_to_detail(row: RuntimeTemplate, *, user: User, db: Session) -> RuntimeTemplateDetailResponse:
    base = template_to_response(row, user=user, db=db).model_dump()
    return RuntimeTemplateDetailResponse(
        **base,
        topology_snapshot=dict(row.topology_snapshot or {}),
    )


def list_templates(
    db: Session,
    user: User,
    *,
    project_id: UUID | None = None,
    category: str | None = None,
    q: str | None = None,
) -> list[RuntimeTemplateResponse]:
    stmt = (
        select(RuntimeTemplate)
        .where(_template_readable_predicate(user.id))
        .order_by(RuntimeTemplate.created_at.desc())
    )
    if project_id is not None:
        stmt = stmt.where(
            or_(RuntimeTemplate.project_id == project_id, RuntimeTemplate.slug.is_not(None))
        )
    if category:
        stmt = stmt.where(RuntimeTemplate.category == category.strip())
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(RuntimeTemplate.name.ilike(like))
    rows = list(db.scalars(stmt).all())
    return [template_to_response(r, user=user, db=db) for r in rows]


def get_template_row_for_user(db: Session, user: User, template_id: UUID) -> RuntimeTemplate:
    row = db.get(RuntimeTemplate, template_id)
    if row is None:
        raise ValueError("not found")
    vis = _template_readable_predicate(user.id)
    ok = db.scalar(select(RuntimeTemplate.id).where(RuntimeTemplate.id == template_id, vis))
    if ok is None:
        raise ValueError("not found")
    return row


def get_template_detail(db: Session, user: User, template_id: UUID) -> RuntimeTemplateDetailResponse:
    row = get_template_row_for_user(db, user, template_id)
    return template_to_detail(row, user=user, db=db)


def create_template_from_topology(
    db: Session,
    user: User,
    topology_id: UUID,
    body: TemplateFromTopologyCreate,
) -> RuntimeTemplateDetailResponse:
    require_topology_editor(db, user, topology_id)
    stmt = (
        select(Topology)
        .where(Topology.id == topology_id)
        .options(selectinload(Topology.nodes), selectinload(Topology.links))
    )
    topo = db.execute(stmt).scalar_one_or_none()
    if topo is None:
        raise ValueError("topology not found")

    vis = body.visibility
    if vis not in (TemplateVisibility.PRIVATE.value, TemplateVisibility.PROJECT.value):
        raise ValueError("invalid visibility")

    if vis == TemplateVisibility.PROJECT.value:
        if topo.project_id is None:
            raise ValueError("topology has no project; use private visibility")
    else:
        # private: still associate with topology's project when present (nullable in schema)
        pass

    snap = build_topology_snapshot(topo)
    tmpl_project_id = topo.project_id if vis == TemplateVisibility.PROJECT.value else None

    row = RuntimeTemplate(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        category=(body.category or "general").strip() or "general",
        tags=[str(t).strip() for t in (body.tags or []) if str(t).strip()][:50],
        owner_user_id=user.id,
        project_id=tmpl_project_id,
        visibility=vis,
        topology_snapshot=snap,
        source_topology_id=topology_id,
        slug=None,
    )
    db.add(row)
    db.flush()
    return template_to_detail(row, user=user, db=db)


def _parse_node_type(raw: str) -> NodeType:
    try:
        return NodeType(raw)
    except ValueError:
        return NodeType.GENERIC


def clone_template_to_topology(
    db: Session,
    user: User,
    template_id: UUID,
    body: TemplateCloneRequest,
) -> Topology:
    t_row = get_template_row_for_user(db, user, template_id)
    snap = t_row.topology_snapshot
    if not snap or snap.get("version") != SNAPSHOT_VERSION:
        raise ValueError("invalid snapshot")

    meta = snap.get("topology") or {}
    pid = body.project_id
    if pid is None:
        proj = default_project_for_user(db, user)
        if proj is None:
            raise ValueError("no project available; pass project_id")
        pid = proj.id
    require_project_editor(db, user, pid)

    name = (body.name or "").strip() or str(meta.get("name") or t_row.name or "From template")
    topo = Topology(
        project_id=pid,
        name=name[:255],
        description=meta.get("description"),
        status=TopologyStatus.DRAFT,
        runtime_target=str(meta.get("runtime_target") or "docker")[:64],
        networking_mode=str(meta.get("networking_mode") or "docker_bridge")[:64],
        config=meta.get("config"),
    )
    db.add(topo)
    db.flush()

    id_map: dict[str, UUID] = {}
    for n in snap.get("nodes") or []:
        key = str(n.get("id") or "")
        if not key:
            continue
        node = TopologyNode(
            topology_id=topo.id,
            name=str(n.get("name") or "node")[:255],
            node_type=_parse_node_type(str(n.get("node_type") or "generic")),
            image=(str(n["image"])[:512] if n.get("image") else None),
            ip_address=(str(n["ip_address"])[:64] if n.get("ip_address") else None),
            config=n.get("config") if isinstance(n.get("config"), dict) else None,
        )
        db.add(node)
        db.flush()
        id_map[key] = node.id

    for ln in snap.get("links") or []:
        sk = str(ln.get("source_id") or "")
        tk = str(ln.get("target_id") or "")
        sid = id_map.get(sk)
        tid = id_map.get(tk)
        if sid is None or tid is None:
            continue
        vlan_tag = None
        if ln.get("vlan_tag") is not None:
            try:
                v = int(ln["vlan_tag"])
                if 0 <= v <= 4094:
                    vlan_tag = v
            except (TypeError, ValueError):
                pass
        link = TopologyLink(
            topology_id=topo.id,
            source_node_id=sid,
            target_node_id=tid,
            network_name=str(ln.get("network_name") or "net")[:255],
            cidr=(str(ln["cidr"])[:64] if ln.get("cidr") else None),
            gateway=(str(ln["gateway"])[:64] if ln.get("gateway") else None),
            vlan_tag=vlan_tag,
            source_endpoint_ip=(str(ln["source_endpoint_ip"])[:64] if ln.get("source_endpoint_ip") else None),
            target_endpoint_ip=(str(ln["target_endpoint_ip"])[:64] if ln.get("target_endpoint_ip") else None),
            config=ln.get("config") if isinstance(ln.get("config"), dict) else None,
        )
        db.add(link)

    db.flush()
    return topo


def delete_template(db: Session, user: User, template_id: UUID) -> None:
    row = db.get(RuntimeTemplate, template_id)
    if row is None:
        raise ValueError("not found")
    if row.slug is not None:
        raise PermissionError("built-in template cannot be deleted")
    if row.owner_user_id == user.id:
        db.delete(row)
        return
    if row.project_id is None:
        raise PermissionError("forbidden")
    role = get_project_membership_role(db, user, row.project_id)
    if role != "owner":
        raise PermissionError("forbidden")
    db.delete(row)
