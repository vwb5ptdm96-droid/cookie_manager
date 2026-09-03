"""add auto_repair_shop_state table (shop-dimension throttle)

Revision ID: 0015_add_auto_repair_shop_state
Revises: 0014_add_auto_repair_ticket
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_add_auto_repair_shop_state"
down_revision = "0014_add_auto_repair_ticket"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("auto_repair_shop_state"):
        return
    op.create_table(
        "auto_repair_shop_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("shop_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("last_dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("budget_day", sa.String(length=8), nullable=True),
        sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # 说明：不建 DB 唯一约束（SQLite 不支持 ALTER 加约束）；(channel, shop_name)
    # 单行由 service 查后插保证（后端单进程 + 修复全局串行，竞态可忽略）。


def downgrade() -> None:
    if _has_table("auto_repair_shop_state"):
        op.drop_table("auto_repair_shop_state")
