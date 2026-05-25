"""Add deployment_targets and external_deployment_jobs (Step 57A).

Revision ID: 20260530_external_deploy
Revises: 20260529_deployment_enum_values
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260530_external_deploy"
down_revision: Union[str, None] = "20260529_deployment_enum_values"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return "users" in tables and "projects" in tables and "topologies" in tables


def upgrade() -> None:
    if _table_exists("deployment_targets"):
        return
    if not _core_tables_present():
        # Fresh install: core tables are created by create_all.
        return

    op.create_table(
        "deployment_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("credentials_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployment_targets_project_id", "deployment_targets", ["project_id"])
    op.create_index("ix_deployment_targets_target_type", "deployment_targets", ["target_type"])
    op.create_index("ix_deployment_targets_status", "deployment_targets", ["status"])
    op.create_index(
        "ix_deployment_targets_created_by_user_id",
        "deployment_targets",
        ["created_by_user_id"],
    )

    op.create_table(
        "external_deployment_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("topology_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("logs", sa.Text(), nullable=True),
        sa.Column("artifact_refs", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["deployment_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_deployment_jobs_project_id",
        "external_deployment_jobs",
        ["project_id"],
    )
    op.create_index(
        "ix_external_deployment_jobs_topology_id",
        "external_deployment_jobs",
        ["topology_id"],
    )
    op.create_index(
        "ix_external_deployment_jobs_target_id",
        "external_deployment_jobs",
        ["target_id"],
    )
    op.create_index("ix_external_deployment_jobs_mode", "external_deployment_jobs", ["mode"])
    op.create_index("ix_external_deployment_jobs_status", "external_deployment_jobs", ["status"])
    op.create_index(
        "ix_external_deployment_jobs_created_by_user_id",
        "external_deployment_jobs",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    if not _core_tables_present():
        return
    if not _table_exists("external_deployment_jobs"):
        return
    op.drop_table("external_deployment_jobs")
    if _table_exists("deployment_targets"):
        op.drop_table("deployment_targets")
