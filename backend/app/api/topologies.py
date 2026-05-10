"""Topology CRUD routes — persistence only; runtime provisioning stays in services layer."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.topology import Topology, TopologyStatus
from app.schemas.topology import TopologyCreate, TopologyResponse

router = APIRouter(prefix="/topologies", tags=["topologies"])


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
