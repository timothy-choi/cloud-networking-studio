"""Normalize deployment.cleanup_status to lowercase enum values.

Revision ID: 20260528_cleanup_enum_values
Revises: 20260527_dep_cleanup
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_cleanup_enum_values"
down_revision: Union[str, None] = "20260527_dep_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _core_tables_present() -> bool:
    bind = op.get_bind()
    return "deployments" in sa.inspect(bind).get_table_names()


def _normalize_cleanup_status_values() -> None:
    """Map legacy uppercase enum names / mixed values to persisted lowercase values."""
    op.execute(
        sa.text(
            """
            UPDATE deployments
            SET cleanup_status = CASE
                WHEN cleanup_status IS NULL THEN 'none'
                WHEN UPPER(TRIM(cleanup_status)) = 'NONE' THEN 'none'
                WHEN UPPER(TRIM(cleanup_status)) = 'CLEAN' THEN 'clean'
                WHEN UPPER(TRIM(cleanup_status)) IN ('PARTIAL_FAILED', 'PARTIAL FAILED') THEN 'partial_failed'
                WHEN LOWER(TRIM(cleanup_status)) = 'none' THEN 'none'
                WHEN LOWER(TRIM(cleanup_status)) = 'clean' THEN 'clean'
                WHEN LOWER(TRIM(cleanup_status)) = 'partial_failed' THEN 'partial_failed'
                ELSE 'none'
            END
            WHERE cleanup_status IS NULL
               OR TRIM(cleanup_status) = ''
               OR cleanup_status NOT IN ('none', 'clean', 'partial_failed')
            """
        )
    )


def upgrade() -> None:
    if not _core_tables_present():
        return
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "cleanup_status" not in dep_cols:
        return
    _normalize_cleanup_status_values()
    op.alter_column(
        "deployments",
        "cleanup_status",
        server_default="none",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Data normalization is not reversed; schema default remains compatible.
    pass
