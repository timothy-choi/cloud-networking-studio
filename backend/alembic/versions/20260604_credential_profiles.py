"""Add credential_profiles table for user-owned cloud credentials."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260604_credential_profiles"
down_revision: Union[str, None] = "20260603_infra_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "credential_profiles" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "credential_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("credential_type", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("validation_message", sa.Text(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credential_profiles_project_id", "credential_profiles", ["project_id"])
    op.create_index("ix_credential_profiles_owner_id", "credential_profiles", ["owner_id"])
    op.create_index("ix_credential_profiles_provider", "credential_profiles", ["provider"])
    op.create_index("ix_credential_profiles_validation_status", "credential_profiles", ["validation_status"])


def downgrade() -> None:
    bind = op.get_bind()
    if "credential_profiles" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_credential_profiles_validation_status", table_name="credential_profiles")
    op.drop_index("ix_credential_profiles_provider", table_name="credential_profiles")
    op.drop_index("ix_credential_profiles_owner_id", table_name="credential_profiles")
    op.drop_index("ix_credential_profiles_project_id", table_name="credential_profiles")
    op.drop_table("credential_profiles")
