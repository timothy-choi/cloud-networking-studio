"""Create project_invitations table (Step 54B).

Revision ID: 20260524_project_invitations
Revises: 20260518_scopes_json
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260524_project_invitations"
down_revision: Union[str, None] = "20260518_scopes_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _core_tables_present() -> bool:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    return "users" in tables and "projects" in tables


def upgrade() -> None:
    if _table_exists("project_invitations"):
        return
    if not _core_tables_present():
        # Fresh install: core tables (and project_invitations) are created by create_all.
        return
    op.create_table(
        "project_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_invitations_email", "project_invitations", ["email"])
    op.create_index("ix_project_invitations_project_id", "project_invitations", ["project_id"])
    op.create_index("ix_project_invitations_status", "project_invitations", ["status"])
    op.create_index(
        "ix_project_invitations_invited_by_user_id",
        "project_invitations",
        ["invited_by_user_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_invitation_pending_email
        ON project_invitations (project_id, email)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    if not _table_exists("project_invitations"):
        return
    op.execute("DROP INDEX IF EXISTS uq_project_invitation_pending_email")
    op.drop_table("project_invitations")
