"""Add infrastructure_deployment_id to deployment_targets.

Revision ID: 20260602_target_infra_link
Revises: 20260601_infra_deploy
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260602_target_infra_link"
down_revision: Union[str, None] = "20260601_infra_deploy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "deployment_targets" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("deployment_targets")}
    if "infrastructure_deployment_id" in cols:
        return
    op.add_column(
        "deployment_targets",
        sa.Column("infrastructure_deployment_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_deployment_targets_infrastructure_deployment_id",
        "deployment_targets",
        ["infrastructure_deployment_id"],
    )
    op.create_foreign_key(
        "fk_deployment_targets_infrastructure_deployment_id",
        "deployment_targets",
        "infrastructure_deployments",
        ["infrastructure_deployment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "deployment_targets" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("deployment_targets")}
    if "infrastructure_deployment_id" not in cols:
        return
    op.drop_constraint(
        "fk_deployment_targets_infrastructure_deployment_id",
        "deployment_targets",
        type_="foreignkey",
    )
    op.drop_index("ix_deployment_targets_infrastructure_deployment_id", "deployment_targets")
    op.drop_column("deployment_targets", "infrastructure_deployment_id")
