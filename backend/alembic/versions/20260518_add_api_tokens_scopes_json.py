"""Add api_tokens.scopes_json for scoped API tokens (Step 53D).

Revision ID: 20260518_scopes_json
Revises:
Create Date: 2026-05-18

Legacy rows keep scopes_json NULL (= full account access).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_scopes_json"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _api_tokens_columns() -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "api_tokens" not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns("api_tokens")}


def upgrade() -> None:
    cols = _api_tokens_columns()
    if not cols:
        # Fresh install: ``api_tokens`` is created by ``create_all`` after migrations run.
        return
    if "scopes_json" not in cols:
        op.add_column("api_tokens", sa.Column("scopes_json", sa.Text(), nullable=True))


def downgrade() -> None:
    cols = _api_tokens_columns()
    if "scopes_json" in cols:
        op.drop_column("api_tokens", "scopes_json")
