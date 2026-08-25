"""drop task_id from profile_registry

Revision ID: 0010_drop_profile_task_id
Revises: 0009_add_repair_cron_expression
Create Date: 2026-08-25 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_drop_profile_task_id"
down_revision = "0009_add_repair_cron_expression"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_column("profile_registry", "task_id"):
        with op.batch_alter_table("profile_registry") as batch_op:
            batch_op.drop_column("task_id")


def downgrade() -> None:
    if not _has_column("profile_registry", "task_id"):
        with op.batch_alter_table("profile_registry") as batch_op:
            batch_op.add_column(sa.Column("task_id", sa.Integer, nullable=True))
