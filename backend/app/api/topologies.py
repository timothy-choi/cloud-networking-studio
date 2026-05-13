"""Topology CRUD routes — persistence only; runtime provisioning stays in services layer."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.topology import (
    Topology,
    TopologyLink,
    TopologyNode,
    TopologyStatus,
)
from app.schemas.topology import (
    TopologyCreate,
    TopologyLinkCreate,
    TopologyLinkResponse,
    TopologyLinkUpdate,
    TopologyNodeCreate,
    TopologyNodeResponse,
    TopologyNodeUpdate,
    TopologyResponse,
    TopologyUpdate,
)

router = APIRouter(prefix="/topologies", tags=["topologies"])


def _merge_json_dict(
    base: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Shallow-merge patch into base (used for node/link config)."""
    if patch is None:
        return base
    if base is None:
        return dict(patch)
    return {**base, **patch}


def _get_topology_or_404(db: Session, topology_id: UUID) -> Topology:
    topo = db.get(Topology, topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    return topo


def _counts_for_topology(db: Session, topology_id: UUID) -> tuple[int, int]:
    n = db.scalar(
        select(sa_func.count()).select_from(TopologyNode).where(TopologyNode.topology_id == topology_id)
    )
    l = db.scalar(
        select(sa_func.count()).select_from(TopologyLink).where(TopologyLink.topology_id == topology_id)
    )
    return (int(n or 0), int(l or 0))


@router.post(
    "",
    response_model=TopologyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create topology",
)
def create_topology(
    body: TopologyCreate,
    db: Session = Depends(get_db),
) -> Topology:
    """Create and persist a topology definition."""
    topo = Topology(
        name=body.name,
        description=body.description,
        status=body.status or TopologyStatus.DRAFT,
        runtime_target=body.runtime_target,
        networking_mode=body.networking_mode,
        config=body.config,
    )
    db.add(topo)
    db.commit()
    db.refresh(topo)
    return topo


@router.get(
    "",
    response_model=list[TopologyResponse],
    summary="List topologies",
)
def list_topologies(db: Session = Depends(get_db)) -> list[TopologyResponse]:
    """List topologies, newest first, with node/link counts for dashboards."""
    stmt = select(Topology).order_by(Topology.created_at.desc())
    rows = list(db.scalars(stmt).all())
    out: list[TopologyResponse] = []
    for topo in rows:
        nc, lc = _counts_for_topology(db, topo.id)
        out.append(
            TopologyResponse.model_validate(topo).model_copy(update={"node_count": nc, "link_count": lc}),
        )
    return out


@router.get(
    "/{topology_id}",
    response_model=TopologyResponse,
    summary="Get topology",
)
def get_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> TopologyResponse:
    """Fetch a single topology by id."""
    topo = db.get(Topology, topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    nc, lc = _counts_for_topology(db, topology_id)
    return TopologyResponse.model_validate(topo).model_copy(update={"node_count": nc, "link_count": lc})


@router.delete(
    "/{topology_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete topology",
)
def delete_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Remove topology row; cascades delete nodes, links, and deployment records."""
    topo = _get_topology_or_404(db, topology_id)
    db.delete(topo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{topology_id}/nodes",
    response_model=TopologyNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create topology node",
)
def create_topology_node(
    topology_id: UUID,
    body: TopologyNodeCreate,
    db: Session = Depends(get_db),
) -> TopologyNode:
    """Add a node to a topology graph."""
    _get_topology_or_404(db, topology_id)
    node = TopologyNode(
        topology_id=topology_id,
        name=body.name,
        node_type=body.node_type,
        image=body.image,
        ip_address=body.ip_address,
        config=body.config,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.get(
    "/{topology_id}/nodes",
    response_model=list[TopologyNodeResponse],
    summary="List topology nodes",
)
def list_topology_nodes(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> list[TopologyNode]:
    """List all nodes belonging to a topology."""
    _get_topology_or_404(db, topology_id)
    stmt = select(TopologyNode).where(TopologyNode.topology_id == topology_id)
    return list(db.scalars(stmt).all())


@router.post(
    "/{topology_id}/links",
    response_model=TopologyLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create topology link",
)
def create_topology_link(
    topology_id: UUID,
    body: TopologyLinkCreate,
    db: Session = Depends(get_db),
) -> TopologyLink:
    """Connect two nodes within the same topology."""
    _get_topology_or_404(db, topology_id)

    src = db.get(TopologyNode, body.source_node_id)
    tgt = db.get(TopologyNode, body.target_node_id)
    if src is None or tgt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    if src.topology_id != topology_id or tgt.topology_id != topology_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    link = TopologyLink(
        topology_id=topology_id,
        source_node_id=body.source_node_id,
        target_node_id=body.target_node_id,
        network_name=body.network_name,
        cidr=body.cidr,
        gateway=body.gateway,
        vlan_tag=body.vlan_tag,
        source_endpoint_ip=body.source_endpoint_ip,
        target_endpoint_ip=body.target_endpoint_ip,
        config=body.config,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get(
    "/{topology_id}/links",
    response_model=list[TopologyLinkResponse],
    summary="List topology links",
)
def list_topology_links(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> list[TopologyLink]:
    """List all links belonging to a topology."""
    _get_topology_or_404(db, topology_id)
    stmt = select(TopologyLink).where(TopologyLink.topology_id == topology_id)
    return list(db.scalars(stmt).all())


@router.patch(
    "/{topology_id}",
    response_model=TopologyResponse,
    summary="Update topology metadata",
)
def patch_topology(
    topology_id: UUID,
    body: TopologyUpdate,
    db: Session = Depends(get_db),
) -> Topology:
    topo = _get_topology_or_404(db, topology_id)
    data = body.model_dump(exclude_unset=True)
    if "config" in data:
        topo.config = _merge_json_dict(topo.config, data.pop("config"))
    for key, val in data.items():
        setattr(topo, key, val)
    db.commit()
    db.refresh(topo)
    return topo


@router.patch(
    "/{topology_id}/nodes/{node_id}",
    response_model=TopologyNodeResponse,
    summary="Update topology node",
)
def patch_topology_node(
    topology_id: UUID,
    node_id: UUID,
    body: TopologyNodeUpdate,
    db: Session = Depends(get_db),
) -> TopologyNode:
    _get_topology_or_404(db, topology_id)
    node = db.get(TopologyNode, node_id)
    if node is None or node.topology_id != topology_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    data = body.model_dump(exclude_unset=True)
    if "config" in data:
        node.config = _merge_json_dict(node.config, data.pop("config"))
    for key, val in data.items():
        setattr(node, key, val)
    db.commit()
    db.refresh(node)
    return node


@router.delete(
    "/{topology_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete topology node",
)
def delete_topology_node(
    topology_id: UUID,
    node_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    _get_topology_or_404(db, topology_id)
    node = db.get(TopologyNode, node_id)
    if node is None or node.topology_id != topology_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    db.delete(node)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{topology_id}/links/{link_id}",
    response_model=TopologyLinkResponse,
    summary="Update topology link",
)
def patch_topology_link(
    topology_id: UUID,
    link_id: UUID,
    body: TopologyLinkUpdate,
    db: Session = Depends(get_db),
) -> TopologyLink:
    _get_topology_or_404(db, topology_id)
    link = db.get(TopologyLink, link_id)
    if link is None or link.topology_id != topology_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    data = body.model_dump(exclude_unset=True)
    if "config" in data:
        link.config = _merge_json_dict(link.config, data.pop("config"))
    for key, val in data.items():
        setattr(link, key, val)
    db.commit()
    db.refresh(link)
    return link


@router.delete(
    "/{topology_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete topology link",
)
def delete_topology_link(
    topology_id: UUID,
    link_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    _get_topology_or_404(db, topology_id)
    link = db.get(TopologyLink, link_id)
    if link is None or link.topology_id != topology_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
