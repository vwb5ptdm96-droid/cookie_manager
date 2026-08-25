"""drop channel and owner_name from profile_registry

Revision ID: 0004_drop_profile_channel_owner
Revises: 0003_drop_legacy_not_null_columns
Create Date: 2026-07-01 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_drop_profile_channel_owner"
down_revision = "0003_drop_legacy_not_null_columns"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _drop_columns_if_present(table_name: str, column_names: list[str]) -> None:
    present = _columns(table_name).intersection(column_names)
    if not present:
        return

    with op.batch_alter_table(table_name) as batch_op:
        for column_name in column_names:
            if column_name in present:
                batch_op.drop_column(column_name)


def upgrade() -> None:
    _drop_columns_if_present("profile_registry", ["channel", "owner_name"])


def downgrade() -> None:
    pass
