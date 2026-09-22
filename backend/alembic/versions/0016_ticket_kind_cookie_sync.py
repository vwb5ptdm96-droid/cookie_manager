"""add auto_repair_ticket.kind + cookie_sync_task_code

Revision ID: 0016_ticket_kind_cookie_sync
Revises: 0015_add_auto_repair_shop_state
Create Date: 2026-09-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_ticket_kind_cookie_sync"
down_revision = "0015_add_auto_repair_shop_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("auto_repair_ticket"):
        return
    cols = {c["name"] for c in inspector.get_columns("auto_repair_ticket")}
    with op.batch_alter_table("auto_repair_ticket") as batch:
        if "kind" not in cols:
            batch.add_column(sa.Column("kind", sa.String(length=32), nullable=False, server_default="auto_repair"))
        if "cookie_sync_task_code" not in cols:
            batch.add_column(sa.Column("cookie_sync_task_code", sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("auto_repair_ticket"):
        return
    cols = {c["name"] for c in inspector.get_columns("auto_repair_ticket")}
    with op.batch_alter_table("auto_repair_ticket") as batch:
        if "cookie_sync_task_code" in cols:
            batch.drop_column("cookie_sync_task_code")
        if "kind" in cols:
            batch.drop_column("kind")
