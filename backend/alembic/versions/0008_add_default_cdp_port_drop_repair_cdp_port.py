"""add default_cdp_port to script_registry, drop repair_cdp_port from health_task

Revision ID: 0008_add_default_cdp_port_drop_repair_cdp_port
Revises: 0007_add_repair_cdp_port
Create Date: 2026-07-03 14:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_add_default_cdp_port_drop_repair_cdp_port"
down_revision = "0007_add_repair_cdp_port"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    # 1. 给 script_registry 加 default_cdp_port
    if not _has_column("script_registry", "default_cdp_port"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.add_column(sa.Column("default_cdp_port", sa.Integer, nullable=True))

    # 2. 从 health_task 删除 repair_cdp_port（如果还在的话）
    if _has_column("health_task", "repair_cdp_port"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.drop_column("repair_cdp_port")


def downgrade() -> None:
    if _has_column("script_registry", "default_cdp_port"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.drop_column("default_cdp_port")

    if not _has_column("health_task", "repair_cdp_port"):
        with op.batch_alter_table("health_task") as batch_op:
            batch_op.add_column(sa.Column("repair_cdp_port", sa.Integer, nullable=True))
