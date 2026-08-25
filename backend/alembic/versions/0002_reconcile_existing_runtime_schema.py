"""reconcile early runtime database with current models

Revision ID: 0002_reconcile_existing_runtime_schema
Revises: 0001_initial_schema
Create Date: 2026-07-01 15:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_reconcile_existing_runtime_schema"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column_name: str, column: sa.Column) -> None:
    if column_name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing(
        "session_maintenance_task",
        "task_name",
        sa.Column("task_name", sa.String(length=128), nullable=False, server_default="未命名任务"),
    )
    _add_column_if_missing(
        "session_maintenance_task",
        "mobile_phone",
        sa.Column("mobile_phone", sa.String(length=32), nullable=False, server_default=""),
    )
    _add_column_if_missing("session_maintenance_task", "account_alias", sa.Column("account_alias", sa.String(length=128), nullable=True))
    _add_column_if_missing(
        "session_maintenance_task",
        "related_dns",
        sa.Column("related_dns", sa.Text(), nullable=False, server_default="[]"),
    )
    _add_column_if_missing(
        "session_maintenance_task",
        "script_code",
        sa.Column("script_code", sa.String(length=64), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "session_maintenance_task",
        "profile_key",
        sa.Column("profile_key", sa.String(length=64), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "session_maintenance_task",
        "schedule_type",
        sa.Column("schedule_type", sa.String(length=32), nullable=False, server_default="MANUAL"),
    )
    _add_column_if_missing("session_maintenance_task", "schedule_value", sa.Column("schedule_value", sa.String(length=128), nullable=True))
    _add_column_if_missing("session_maintenance_task", "script_config", sa.Column("script_config", sa.Text(), nullable=True))
    _add_column_if_missing(
        "session_maintenance_task",
        "enabled",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column_if_missing("session_maintenance_task", "last_run_status", sa.Column("last_run_status", sa.String(length=32), nullable=True))
    _add_column_if_missing("session_maintenance_task", "last_run_id", sa.Column("last_run_id", sa.String(length=64), nullable=True))
    _add_column_if_missing("session_maintenance_task", "last_error", sa.Column("last_error", sa.Text(), nullable=True))
    _add_column_if_missing("session_maintenance_task", "last_artifact_dir", sa.Column("last_artifact_dir", sa.String(length=255), nullable=True))
    _add_column_if_missing("session_maintenance_task", "last_run_at", sa.Column("last_run_at", sa.DateTime(), nullable=True))

    task_columns = _columns("session_maintenance_task")
    if {"account_label", "task_name"}.issubset(task_columns):
        op.execute("UPDATE session_maintenance_task SET task_name = account_label WHERE task_name = '未命名任务'")
    if {"profile_code", "profile_key"}.issubset(task_columns):
        op.execute("UPDATE session_maintenance_task SET profile_key = profile_code WHERE profile_key = ''")

    _add_column_if_missing("profile_registry", "task_id", sa.Column("task_id", sa.Integer(), nullable=True))

    _add_column_if_missing(
        "health_check_config",
        "cookie_table",
        sa.Column("cookie_table", sa.String(length=128), nullable=False, server_default="ods_cookie_playwright"),
    )
    _add_column_if_missing("health_check_config", "channel", sa.Column("channel", sa.String(length=32), nullable=False, server_default=""))
    _add_column_if_missing("health_check_config", "shop_name", sa.Column("shop_name", sa.String(length=128), nullable=False, server_default=""))
    _add_column_if_missing("health_check_config", "mobile_phone", sa.Column("mobile_phone", sa.String(length=32), nullable=False, server_default=""))
    _add_column_if_missing("health_check_config", "dns", sa.Column("dns", sa.String(length=128), nullable=False, server_default=""))
    _add_column_if_missing("health_check_config", "method", sa.Column("method", sa.String(length=16), nullable=False, server_default="GET"))
    _add_column_if_missing("health_check_config", "check_url", sa.Column("check_url", sa.String(length=500), nullable=False, server_default=""))
    _add_column_if_missing("health_check_config", "request_headers", sa.Column("request_headers", sa.Text(), nullable=True))
    _add_column_if_missing("health_check_config", "request_body", sa.Column("request_body", sa.Text(), nullable=True))
    _add_column_if_missing("health_check_config", "success_rule", sa.Column("success_rule", sa.Text(), nullable=True))
    _add_column_if_missing("health_check_config", "failure_rule", sa.Column("failure_rule", sa.Text(), nullable=True))
    _add_column_if_missing("health_check_config", "trigger_task_id", sa.Column("trigger_task_id", sa.Integer(), nullable=True))
    _add_column_if_missing("health_check_config", "status", sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"))
    _add_column_if_missing("health_check_config", "last_result_message", sa.Column("last_result_message", sa.Text(), nullable=True))
    _add_column_if_missing("health_check_config", "last_checked_at", sa.Column("last_checked_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(
        "health_check_config",
        "updated_at",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    _add_column_if_missing(
        "manual_repair_ticket",
        "profile_key",
        sa.Column("profile_key", sa.String(length=64), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "manual_repair_ticket",
        "risk_type",
        sa.Column("risk_type", sa.String(length=64), nullable=False, server_default="RISK"),
    )
    _add_column_if_missing(
        "manual_repair_ticket",
        "risk_message",
        sa.Column("risk_message", sa.Text(), nullable=False, server_default=""),
    )
    _add_column_if_missing("manual_repair_ticket", "repaired_by", sa.Column("repaired_by", sa.String(length=128), nullable=True))
    _add_column_if_missing("manual_repair_ticket", "browser_artifact_dir", sa.Column("browser_artifact_dir", sa.String(length=255), nullable=True))
    _add_column_if_missing("manual_repair_ticket", "browser_opened_at", sa.Column("browser_opened_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("manual_repair_ticket", "closed_at", sa.Column("closed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(
        "manual_repair_ticket",
        "updated_at",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    ticket_columns = _columns("manual_repair_ticket")
    if {"reason", "risk_message"}.issubset(ticket_columns):
        op.execute("UPDATE manual_repair_ticket SET risk_message = reason WHERE risk_message = ''")

    _add_column_if_missing("task_run_log", "task_id", sa.Column("task_id", sa.Integer(), nullable=True))
    _add_column_if_missing("task_run_log", "check_id", sa.Column("check_id", sa.Integer(), nullable=True))
    _add_column_if_missing("task_run_log", "ticket_id", sa.Column("ticket_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    # SQLite cannot safely drop these compatibility columns without table rebuilds.
    pass
