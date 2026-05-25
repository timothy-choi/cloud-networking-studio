"""Add infrastructure deployment tables (Step 57C).

Revision ID: 20260601_infra_deploy
Revises: 20260531_ext_deployments
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_infra_deploy"
down_revision: Union[str, None] = "20260531_ext_deployments"
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
    if _table_exists("infrastructure_deployments"):
        return
    if not _core_tables_present():
        return

    op.create_table(
        "infrastructure_deployments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("topology_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("stack_type", sa.String(length=32), nullable=False, server_default="terraform_ansible"),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("variables_json", sa.JSON(), nullable=False),
        sa.Column("plan_summary_json", sa.JSON(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=False),
        sa.Column("inventory_json", sa.JSON(), nullable=False),
        sa.Column("state_metadata_json", sa.JSON(), nullable=False),
        sa.Column("events_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("runtime_targets_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_infrastructure_deployments_project_id", "infrastructure_deployments", ["project_id"])
    op.create_index("ix_infrastructure_deployments_topology_id", "infrastructure_deployments", ["topology_id"])
    op.create_index("ix_infrastructure_deployments_template_id", "infrastructure_deployments", ["template_id"])
    op.create_index("ix_infrastructure_deployments_provider", "infrastructure_deployments", ["provider"])
    op.create_index("ix_infrastructure_deployments_status", "infrastructure_deployments", ["status"])

    op.create_table(
        "infrastructure_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("infrastructure_deployment_id", sa.Uuid(), nullable=False),
        sa.Column("execution_type", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("runner_execution_id", sa.String(length=64), nullable=True),
        sa.Column("logs", sa.Text(), nullable=True),
        sa.Column("artifact_refs", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["infrastructure_deployment_id"],
            ["infrastructure_deployments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_infrastructure_executions_deployment_id",
        "infrastructure_executions",
        ["infrastructure_deployment_id"],
    )
    op.create_index("ix_infrastructure_executions_execution_type", "infrastructure_executions", ["execution_type"])
    op.create_index("ix_infrastructure_executions_mode", "infrastructure_executions", ["mode"])
    op.create_index("ix_infrastructure_executions_status", "infrastructure_executions", ["status"])
    op.create_index(
        "ix_infrastructure_executions_runner_execution_id",
        "infrastructure_executions",
        ["runner_execution_id"],
    )


def downgrade() -> None:
    if not _core_tables_present():
        return
    if _table_exists("infrastructure_executions"):
        op.drop_table("infrastructure_executions")
    if _table_exists("infrastructure_deployments"):
        op.drop_table("infrastructure_deployments")
