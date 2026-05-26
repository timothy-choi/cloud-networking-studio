"""Add credentials_ref to infrastructure deployments (Step 57D).

Revision ID: 20260603_infra_credentials
Revises: 20260602_target_infra_link
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260603_infra_credentials"
down_revision: Union[str, None] = "20260602_target_infra_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _column_exists("infrastructure_deployments", "credentials_ref"):
        op.add_column(
            "infrastructure_deployments",
            sa.Column("credentials_ref", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("infrastructure_deployments", "credentials_ref"):
        op.drop_column("infrastructure_deployments", "credentials_ref")
