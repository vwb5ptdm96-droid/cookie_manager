"""add profile_key to script_registry

Revision ID: 0005_add_script_profile_key
Revises: 0004_drop_profile_channel_owner
Create Date: 2026-07-01 16:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_add_script_profile_key"
down_revision = "0004_drop_profile_channel_owner"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("script_registry", "profile_key"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.add_column(sa.Column("profile_key", sa.String(64), nullable=True))


def downgrade() -> None:
    if _has_column("script_registry", "profile_key"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.drop_column("profile_key")
