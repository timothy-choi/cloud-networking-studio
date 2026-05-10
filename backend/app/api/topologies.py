"""Topology CRUD routes — persistence only; runtime provisioning stays in services layer."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    TopologyNodeCreate,
    TopologyNodeResponse,
    TopologyResponse,
)

router = APIRouter(prefix="/topologies", tags=["topologies"])


def _get_topology_or_404(db: Session, topology_id: UUID) -> Topology:
    topo = db.get(Topology, topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    return topo


@router.post(
    "",
    response_model=TopologyResponse,
    status_code=status.HTTP_201_CREATED,
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


@router.get("", response_model=list[TopologyResponse])
def list_topologies(db: Session = Depends(get_db)) -> list[Topology]:
    """List topologies, newest first."""
    stmt = select(Topology).order_by(Topology.created_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/{topology_id}", response_model=TopologyResponse)
def get_topology(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> Topology:
    """Fetch a single topology by id."""
    topo = db.get(Topology, topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    return topo


@router.post(
    "/{topology_id}/nodes",
    response_model=TopologyNodeResponse,
    status_code=status.HTTP_201_CREATED,
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


@router.get("/{topology_id}/nodes", response_model=list[TopologyNodeResponse])
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
        config=body.config,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/{topology_id}/links", response_model=list[TopologyLinkResponse])
def list_topology_links(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> list[TopologyLink]:
    """List all links belonging to a topology."""
    _get_topology_or_404(db, topology_id)
    stmt = select(TopologyLink).where(TopologyLink.topology_id == topology_id)
    return list(db.scalars(stmt).all())
