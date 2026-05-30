"""Add external_deployments table (Step 57B).

Revision ID: 20260531_ext_deployments
Revises: 20260530_external_deploy
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_ext_deployments"
down_revision: Union[str, None] = "20260530_external_deploy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return (
        "users" in tables
        and "projects" in tables
        and "topologies" in tables
        and "deployment_targets" in tables
        and "external_deployment_jobs" in tables
    )


def upgrade() -> None:
    if _table_exists("external_deployments"):
        return
    if not _core_tables_present():
        return

    op.create_table(
        "external_deployments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("topology_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("compose_project_name", sa.String(length=128), nullable=False),
        sa.Column("remote_workdir", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("services_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["external_deployment_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["deployment_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_deployments_project_id", "external_deployments", ["project_id"])
    op.create_index("ix_external_deployments_topology_id", "external_deployments", ["topology_id"])
    op.create_index("ix_external_deployments_target_id", "external_deployments", ["target_id"])
    op.create_index("ix_external_deployments_job_id", "external_deployments", ["job_id"])
    op.create_index("ix_external_deployments_status", "external_deployments", ["status"])


def downgrade() -> None:
    if not _core_tables_present():
        return
    if not _table_exists("external_deployments"):
        return
    op.drop_table("external_deployments")
