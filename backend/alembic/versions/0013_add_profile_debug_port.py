"""add profile_registry debug_port

Revision ID: 0013_add_profile_debug_port
Revises: 0012_add_cookie_sync_task_deadline
Create Date: 2026-08-26 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_add_profile_debug_port"
down_revision = "0012_add_cookie_sync_task_deadline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("profile_registry"):
        with op.batch_alter_table("profile_registry") as batch:
            batch.add_column(sa.Column("debug_port", sa.Integer(), nullable=True))


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("profile_registry"):
        with op.batch_alter_table("profile_registry") as batch:
            batch.drop_column("debug_port")
