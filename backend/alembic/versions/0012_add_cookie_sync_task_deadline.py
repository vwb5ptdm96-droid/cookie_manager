"""add cookie_sync_task sync_deadline_at

Revision ID: 0012_add_cookie_sync_task_deadline
Revises: 0011_add_cookie_sync_tables
Create Date: 2026-08-26 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_add_cookie_sync_task_deadline"
down_revision = "0011_add_cookie_sync_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("cookie_sync_task"):
        with op.batch_alter_table("cookie_sync_task") as batch:
            batch.add_column(sa.Column("sync_deadline_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("cookie_sync_task"):
        with op.batch_alter_table("cookie_sync_task") as batch:
            batch.drop_column("sync_deadline_at")
