"""add auto_repair_ticket table

Revision ID: 0014_add_auto_repair_ticket
Revises: 0013_add_profile_debug_port
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_add_auto_repair_ticket"
down_revision = "0013_add_profile_debug_port"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("auto_repair_ticket"):
        return
    op.create_table(
        "auto_repair_ticket",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("shop_name", sa.String(length=128), nullable=True),
        sa.Column("cdp_port", sa.Integer(), nullable=False, server_default="9222"),
        sa.Column("script_code", sa.String(length=64), nullable=True),
        sa.Column("health_task_code", sa.String(length=64), nullable=True),
        sa.Column("script_run_id", sa.Integer(), nullable=True),
        sa.Column("issue_type", sa.String(length=16), nullable=False, server_default="FAIL"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_day", sa.String(length=8), nullable=True),
        sa.Column("last_dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    if _has_table("auto_repair_ticket"):
        op.drop_table("auto_repair_ticket")
