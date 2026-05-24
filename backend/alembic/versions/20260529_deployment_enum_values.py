"""Normalize deployment enum columns to lowercase persisted values.

Revision ID: 20260529_deployment_enum_values
Revises: 20260528_cleanup_enum_values
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_deployment_enum_values"
down_revision: Union[str, None] = "20260528_cleanup_enum_values"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _core_tables_present() -> bool:
    bind = op.get_bind()
    return "deployments" in sa.inspect(bind).get_table_names()


def _normalize_deployment_status_values() -> None:
    op.execute(
        sa.text(
            """
            UPDATE deployments
            SET status = CASE
                WHEN status IS NULL THEN 'pending'
                WHEN UPPER(TRIM(status)) = 'PENDING' THEN 'pending'
                WHEN UPPER(TRIM(status)) = 'DEPLOYING' THEN 'deploying'
                WHEN UPPER(TRIM(status)) = 'SUCCEEDED' THEN 'succeeded'
                WHEN UPPER(TRIM(status)) = 'FAILED' THEN 'failed'
                WHEN UPPER(TRIM(status)) = 'STOPPING' THEN 'stopping'
                WHEN UPPER(TRIM(status)) IN ('STOPPED', 'DESTROYED') THEN 'stopped'
                WHEN LOWER(TRIM(status)) = 'pending' THEN 'pending'
                WHEN LOWER(TRIM(status)) = 'deploying' THEN 'deploying'
                WHEN LOWER(TRIM(status)) = 'succeeded' THEN 'succeeded'
                WHEN LOWER(TRIM(status)) = 'failed' THEN 'failed'
                WHEN LOWER(TRIM(status)) = 'stopping' THEN 'stopping'
                WHEN LOWER(TRIM(status)) IN ('stopped', 'destroyed') THEN 'stopped'
                ELSE 'pending'
            END
            WHERE status IS NULL
               OR TRIM(status) = ''
               OR status NOT IN (
                   'pending', 'deploying', 'succeeded', 'failed', 'stopping', 'stopped'
               )
            """
        )
    )


def _normalize_topology_sync_status_values() -> None:
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "topology_sync_status" not in dep_cols:
        return
    op.execute(
        sa.text(
            """
            UPDATE deployments
            SET topology_sync_status = CASE
                WHEN topology_sync_status IS NULL THEN 'in_sync'
                WHEN UPPER(TRIM(topology_sync_status)) IN ('IN_SYNC', 'INSYNC') THEN 'in_sync'
                WHEN UPPER(TRIM(topology_sync_status)) IN ('OUT_OF_SYNC', 'OUTOFSYNC') THEN 'out_of_sync'
                WHEN LOWER(TRIM(topology_sync_status)) = 'in_sync' THEN 'in_sync'
                WHEN LOWER(TRIM(topology_sync_status)) = 'out_of_sync' THEN 'out_of_sync'
                ELSE 'in_sync'
            END
            WHERE topology_sync_status IS NULL
               OR TRIM(topology_sync_status) = ''
               OR topology_sync_status NOT IN ('in_sync', 'out_of_sync')
            """
        )
    )


def _normalize_cleanup_status_values() -> None:
    insp = sa.inspect(op.get_bind())
    dep_cols = {c["name"] for c in insp.get_columns("deployments")}
    if "cleanup_status" not in dep_cols:
        return
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
    _normalize_deployment_status_values()
    _normalize_topology_sync_status_values()
    _normalize_cleanup_status_values()


def downgrade() -> None:
    pass
