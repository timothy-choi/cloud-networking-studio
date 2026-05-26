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


def upgrade() -> None:
    bind = op.get_bind()
    if "infrastructure_deployments" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("infrastructure_deployments")}
    if "credentials_ref" in cols:
        return
    op.add_column(
        "infrastructure_deployments",
        sa.Column("credentials_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "infrastructure_deployments" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("infrastructure_deployments")}
    if "credentials_ref" not in cols:
        return
    op.drop_column("infrastructure_deployments", "credentials_ref")
