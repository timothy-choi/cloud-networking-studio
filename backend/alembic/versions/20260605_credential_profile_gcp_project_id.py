"""Add gcp_project_id to credential_profiles for Terraform project_id resolution."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_credential_profile_gcp_project_id"
down_revision: Union[str, None] = "20260604_credential_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return "users" in tables and "projects" in tables


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _table_exists("credential_profiles"):
        return
    if not _core_tables_present():
        return
    if _column_exists("credential_profiles", "gcp_project_id"):
        return
    op.add_column(
        "credential_profiles",
        sa.Column("gcp_project_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    if not _table_exists("credential_profiles"):
        return
    if not _column_exists("credential_profiles", "gcp_project_id"):
        return
    op.drop_column("credential_profiles", "gcp_project_id")
