"""add repair_cdp_port to health_task

Revision ID: 0007_add_repair_cdp_port
Revises: 0006_add_health_task_script_run
Create Date: 2026-07-03 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_add_repair_cdp_port"
down_revision = "0006_add_health_task_script_run"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("health_task", "repair_cdp_port"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.add_column(sa.Column("repair_cdp_port", sa.Integer, nullable=True))


def downgrade() -> None:
    if _has_column("health_task", "repair_cdp_port"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.drop_column("repair_cdp_port")
