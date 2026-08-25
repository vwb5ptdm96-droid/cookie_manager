"""add repair_cron_expression to health_task

Revision ID: 0009_add_repair_cron_expression
Revises: 0008_add_default_cdp_port_drop_repair_cdp_port
Create Date: 2026-08-25 17:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_repair_cron_expression"
down_revision = "0008_add_default_cdp_port_drop_repair_cdp_port"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("health_task", "repair_cron_expression"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.add_column(sa.Column("repair_cron_expression", sa.String(128), nullable=True))


def downgrade() -> None:
    if _has_column("health_task", "repair_cron_expression"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.drop_column("repair_cron_expression")
