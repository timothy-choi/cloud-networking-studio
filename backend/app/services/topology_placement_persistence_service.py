"""Persistence helpers for topology placement plans and constraints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.topology_placement import TopologyPlacementConstraint, TopologyPlacementPlan
from app.models.user import User


def list_constraints(db: Session, topology_id: UUID) -> list[TopologyPlacementConstraint]:
    return list(
        db.scalars(
            select(TopologyPlacementConstraint)
            .where(TopologyPlacementConstraint.topology_id == topology_id)
            .order_by(TopologyPlacementConstraint.created_at.asc())
        ).all()
    )


def constraints_as_dicts(db: Session, topology_id: UUID) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row.id),
            "constraint_type": row.constraint_type,
            "node_a": row.node_a,
            "node_b": row.node_b,
            "preferred_host": row.preferred_host,
        }
        for row in list_constraints(db, topology_id)
    ]


def create_constraint(
    db: Session,
    *,
    topology_id: UUID,
    project_id: UUID,
    actor: User,
    constraint_type: str,
    node_a: str,
    node_b: str | None = None,
    preferred_host: int | None = None,
) -> TopologyPlacementConstraint:
    row = TopologyPlacementConstraint(
        project_id=project_id,
        topology_id=topology_id,
        constraint_type=constraint_type,
        node_a=node_a.strip(),
        node_b=node_b.strip() if node_b else None,
        preferred_host=preferred_host,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def delete_constraint(
    db: Session,
    *,
    topology_id: UUID,
    constraint_id: UUID,
) -> TopologyPlacementConstraint | None:
    row = db.get(TopologyPlacementConstraint, constraint_id)
    if row is None or row.topology_id != topology_id:
        return None
    db.delete(row)
    db.flush()
    return row


def save_plan(
    db: Session,
    *,
    topology_id: UUID,
    project_id: UUID,
    actor: User,
    plan: dict[str, Any],
) -> TopologyPlacementPlan:
    row = TopologyPlacementPlan(
        project_id=project_id,
        topology_id=topology_id,
        provider=str(plan.get("provider") or "gcp"),
        placement_mode=str(plan.get("placement_mode") or "first_fit"),
        machine_type=str(plan.get("recommended_machine_type") or ""),
        host_count=int(plan.get("recommended_host_count") or len(plan.get("hosts") or []) or 0),
        plan_json=plan,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    plan["id"] = str(row.id)
    row.plan_json = plan
    return row
