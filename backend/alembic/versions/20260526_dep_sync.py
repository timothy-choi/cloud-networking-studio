"""Add deployment topology_sync_status (Step 56 rollback).

Revision ID: 20260526_dep_sync
Revises: 20260525_topo_versions
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_dep_sync"
down_revision: Union[str, None] = "20260525_topo_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return "deployments" in tables


def upgrade() -> None:
    if not _core_tables_present():
        return
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "topology_sync_status" not in dep_cols:
        op.add_column(
            "deployments",
            sa.Column(
                "topology_sync_status",
                sa.String(length=32),
                nullable=False,
                server_default="in_sync",
            ),
        )
        op.create_index("ix_deployments_topology_sync_status", "deployments", ["topology_sync_status"])
        op.alter_column("deployments", "topology_sync_status", server_default=None)


def downgrade() -> None:
    if not _table_exists("deployments"):
        return
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "topology_sync_status" in dep_cols:
        op.drop_index("ix_deployments_topology_sync_status", table_name="deployments")
        op.drop_column("deployments", "topology_sync_status")
