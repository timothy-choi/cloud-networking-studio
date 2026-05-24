"""Add topology versions and deployment profiles (Step 56).

Revision ID: 20260525_topo_versions
Revises: 20260524_project_invitations
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_topo_versions"
down_revision: Union[str, None] = "20260524_project_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return "users" in tables and "topologies" in tables


def upgrade() -> None:
    if not _core_tables_present():
        return
    if not _table_exists("topology_versions"):
        op.create_table(
            "topology_versions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("topology_id", sa.Uuid(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("snapshot_json", sa.JSON(), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("parent_version_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["parent_version_id"], ["topology_versions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_topology_versions_topology_id", "topology_versions", ["topology_id"])
        op.create_index("ix_topology_versions_version_number", "topology_versions", ["version_number"])
        op.create_index("ix_topology_versions_source", "topology_versions", ["source"])
        op.create_index(
            "ix_topology_versions_created_by_user_id",
            "topology_versions",
            ["created_by_user_id"],
        )

    if not _table_exists("deployment_profiles"):
        op.create_table(
            "deployment_profiles",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("topology_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("profile_type", sa.String(length=32), nullable=False),
            sa.Column("config_json", sa.JSON(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_deployment_profiles_topology_id", "deployment_profiles", ["topology_id"])
        op.create_index("ix_deployment_profiles_profile_type", "deployment_profiles", ["profile_type"])
        op.create_index("ix_deployment_profiles_is_default", "deployment_profiles", ["is_default"])

    if _table_exists("deployments"):
        insp = sa.inspect(op.get_bind())
        dep_cols = {c["name"] for c in insp.get_columns("deployments")}
        if "topology_version_id" not in dep_cols:
            op.add_column(
                "deployments",
                sa.Column("topology_version_id", sa.Uuid(), nullable=True),
            )
            op.create_foreign_key(
                "fk_deployments_topology_version_id",
                "deployments",
                "topology_versions",
                ["topology_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index("ix_deployments_topology_version_id", "deployments", ["topology_version_id"])
        if "deployment_profile_id" not in dep_cols:
            op.add_column(
                "deployments",
                sa.Column("deployment_profile_id", sa.Uuid(), nullable=True),
            )
            op.create_foreign_key(
                "fk_deployments_deployment_profile_id",
                "deployments",
                "deployment_profiles",
                ["deployment_profile_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index("ix_deployments_deployment_profile_id", "deployments", ["deployment_profile_id"])
        if "effective_config_json" not in dep_cols:
            op.add_column(
                "deployments",
                sa.Column("effective_config_json", sa.JSON(), nullable=True),
            )


def downgrade() -> None:
    if not _table_exists("deployments"):
        pass
    else:
        insp = sa.inspect(op.get_bind())
        dep_cols = {c["name"] for c in insp.get_columns("deployments")}
        if "effective_config_json" in dep_cols:
            op.drop_column("deployments", "effective_config_json")
        if "deployment_profile_id" in dep_cols:
            op.drop_index("ix_deployments_deployment_profile_id", table_name="deployments")
            op.drop_constraint("fk_deployments_deployment_profile_id", "deployments", type_="foreignkey")
            op.drop_column("deployments", "deployment_profile_id")
        if "topology_version_id" in dep_cols:
            op.drop_index("ix_deployments_topology_version_id", table_name="deployments")
            op.drop_constraint("fk_deployments_topology_version_id", "deployments", type_="foreignkey")
            op.drop_column("deployments", "topology_version_id")
    if _table_exists("deployment_profiles"):
        op.drop_table("deployment_profiles")
    if _table_exists("topology_versions"):
        op.drop_table("topology_versions")
