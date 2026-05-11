"""Traffic test APIs — ping and HTTP checks between deployed nodes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.topology import Topology
from app.schemas.traffic_test import (
    HttpTrafficTestRequest,
    PingTrafficTestRequest,
    TrafficTestResponse,
)
from app.services import traffic_test_service as tt_svc

router = APIRouter(tags=["traffic-tests"])


def _topology_or_404(db: Session, topology_id: UUID) -> Topology:
    topo = db.get(Topology, topology_id)
    if topo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topology not found",
        )
    return topo


@router.post(
    "/topologies/{topology_id}/traffic-tests/ping",
    response_model=TrafficTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run ICMP ping traffic test",
)
def create_ping_traffic_test(
    topology_id: UUID,
    body: PingTrafficTestRequest,
    db: Session = Depends(get_db),
) -> TrafficTestResponse:
    _topology_or_404(db, topology_id)
    try:
        tt = tt_svc.run_ping_test(
            db,
            topology_id,
            body.source_node_id,
            body.target_node_id,
            count=body.count,
        )
    except LookupError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    db.commit()
    loaded = tt_svc.get_traffic_test(db, tt.id)
    assert loaded is not None
    return loaded


@router.post(
    "/topologies/{topology_id}/traffic-tests/http",
    response_model=TrafficTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run HTTP traffic test",
)
def create_http_traffic_test(
    topology_id: UUID,
    body: HttpTrafficTestRequest,
    db: Session = Depends(get_db),
) -> TrafficTestResponse:
    _topology_or_404(db, topology_id)
    try:
        tt = tt_svc.run_http_test(
            db,
            topology_id,
            body.source_node_id,
            body.target_node_id,
            path=body.path,
            port=body.port,
        )
    except LookupError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    db.commit()
    loaded = tt_svc.get_traffic_test(db, tt.id)
    assert loaded is not None
    return loaded


@router.get(
    "/traffic-tests/{traffic_test_id}",
    response_model=TrafficTestResponse,
    summary="Get traffic test",
)
def get_traffic_test(
    traffic_test_id: UUID,
    db: Session = Depends(get_db),
) -> TrafficTestResponse:
    tt = tt_svc.get_traffic_test(db, traffic_test_id)
    if tt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic test not found",
        )
    return tt


@router.get(
    "/topologies/{topology_id}/traffic-tests",
    response_model=list[TrafficTestResponse],
    summary="List topology traffic tests",
)
def list_topology_traffic_tests(
    topology_id: UUID,
    db: Session = Depends(get_db),
) -> list[TrafficTestResponse]:
    _topology_or_404(db, topology_id)
    return tt_svc.list_traffic_tests_for_topology(db, topology_id)
