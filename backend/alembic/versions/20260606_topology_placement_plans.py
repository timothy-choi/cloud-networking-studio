"""Add persisted topology placement plans and constraints."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260606_topology_placement_plans"
down_revision: Union[str, None] = "20260605_gcp_project_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _core_tables_present() -> bool:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    return {"projects", "topologies", "users"}.issubset(tables)


def upgrade() -> None:
    if not _core_tables_present():
        return
    if not _table_exists("topology_placement_constraints"):
        op.create_table(
            "topology_placement_constraints",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("topology_id", sa.Uuid(), nullable=False),
            sa.Column("constraint_type", sa.String(length=32), nullable=False),
            sa.Column("node_a", sa.String(length=255), nullable=False),
            sa.Column("node_b", sa.String(length=255), nullable=True),
            sa.Column("preferred_host", sa.Integer(), nullable=True),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_topology_placement_constraints_project_id", "topology_placement_constraints", ["project_id"])
        op.create_index("ix_topology_placement_constraints_topology_id", "topology_placement_constraints", ["topology_id"])
        op.create_index("ix_topology_placement_constraints_constraint_type", "topology_placement_constraints", ["constraint_type"])

    if not _table_exists("topology_placement_plans"):
        op.create_table(
            "topology_placement_plans",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("topology_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("placement_mode", sa.String(length=32), nullable=False),
            sa.Column("machine_type", sa.String(length=64), nullable=False),
            sa.Column("host_count", sa.Integer(), nullable=False),
            sa.Column("plan_json", sa.JSON(), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_topology_placement_plans_project_id", "topology_placement_plans", ["project_id"])
        op.create_index("ix_topology_placement_plans_topology_id", "topology_placement_plans", ["topology_id"])
        op.create_index("ix_topology_placement_plans_provider", "topology_placement_plans", ["provider"])
        op.create_index("ix_topology_placement_plans_placement_mode", "topology_placement_plans", ["placement_mode"])

    if _table_exists("infrastructure_deployments") and not _column_exists("infrastructure_deployments", "placement_plan_id"):
        op.add_column("infrastructure_deployments", sa.Column("placement_plan_id", sa.Uuid(), nullable=True))
        op.create_index("ix_infrastructure_deployments_placement_plan_id", "infrastructure_deployments", ["placement_plan_id"])
        op.create_foreign_key(
            "fk_infrastructure_deployments_placement_plan_id",
            "infrastructure_deployments",
            "topology_placement_plans",
            ["placement_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _table_exists("infrastructure_deployments") and _column_exists("infrastructure_deployments", "placement_plan_id"):
        op.drop_constraint("fk_infrastructure_deployments_placement_plan_id", "infrastructure_deployments", type_="foreignkey")
        op.drop_index("ix_infrastructure_deployments_placement_plan_id", table_name="infrastructure_deployments")
        op.drop_column("infrastructure_deployments", "placement_plan_id")
    if _table_exists("topology_placement_plans"):
        op.drop_index("ix_topology_placement_plans_placement_mode", table_name="topology_placement_plans")
        op.drop_index("ix_topology_placement_plans_provider", table_name="topology_placement_plans")
        op.drop_index("ix_topology_placement_plans_topology_id", table_name="topology_placement_plans")
        op.drop_index("ix_topology_placement_plans_project_id", table_name="topology_placement_plans")
        op.drop_table("topology_placement_plans")
    if _table_exists("topology_placement_constraints"):
        op.drop_index("ix_topology_placement_constraints_constraint_type", table_name="topology_placement_constraints")
        op.drop_index("ix_topology_placement_constraints_topology_id", table_name="topology_placement_constraints")
        op.drop_index("ix_topology_placement_constraints_project_id", table_name="topology_placement_constraints")
        op.drop_table("topology_placement_constraints")
