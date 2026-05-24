"""Add deployment cleanup_status for destroy/rollback teardown.

Revision ID: 20260527_dep_cleanup
Revises: 20260526_dep_sync
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_dep_cleanup"
down_revision: Union[str, None] = "20260526_dep_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _core_tables_present() -> bool:
    bind = op.get_bind()
    return "deployments" in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _core_tables_present():
        return
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "cleanup_status" not in dep_cols:
        op.add_column(
            "deployments",
            sa.Column(
                "cleanup_status",
                sa.String(length=32),
                nullable=False,
                server_default="none",
            ),
        )
        op.create_index("ix_deployments_cleanup_status", "deployments", ["cleanup_status"])
        op.alter_column("deployments", "cleanup_status", server_default=None)


def downgrade() -> None:
    if not _core_tables_present():
        return
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "cleanup_status" in dep_cols:
        op.drop_index("ix_deployments_cleanup_status", table_name="deployments")
        op.drop_column("deployments", "cleanup_status")
