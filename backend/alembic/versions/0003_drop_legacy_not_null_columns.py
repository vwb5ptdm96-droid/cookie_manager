"""drop legacy not-null columns from early runtime database

Revision ID: 0003_drop_legacy_not_null_columns
Revises: 0002_reconcile_existing_runtime_schema
Create Date: 2026-07-01 15:25:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_drop_legacy_not_null_columns"
down_revision = "0002_reconcile_existing_runtime_schema"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _drop_columns_if_present(table_name: str, column_names: list[str]) -> None:
    present = _columns(table_name).intersection(column_names)
    if not present:
        return

    with op.batch_alter_table(table_name) as batch_op:
        for column_name in column_names:
            if column_name in present:
                batch_op.drop_column(column_name)


def upgrade() -> None:
    _drop_columns_if_present("session_maintenance_task", ["account_label", "profile_code"])
    _drop_columns_if_present("manual_repair_ticket", ["reason"])
    _drop_columns_if_present("health_check_config", ["check_type"])


def downgrade() -> None:
    pass
