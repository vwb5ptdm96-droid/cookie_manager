"""initial schema aligned with current ORM models

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_maintenance_task",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("task_name", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("mobile_phone", sa.String(length=32), nullable=False),
        sa.Column("account_alias", sa.String(length=128), nullable=True),
        sa.Column("related_dns", sa.Text(), nullable=False),
        sa.Column("script_code", sa.String(length=64), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("schedule_type", sa.String(length=32), nullable=False),
        sa.Column("schedule_value", sa.String(length=128), nullable=True),
        sa.Column("script_config", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_artifact_dir", sa.String(length=255), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "health_check_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("check_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("check_name", sa.String(length=128), nullable=False),
        sa.Column("cookie_table", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("shop_name", sa.String(length=128), nullable=False),
        sa.Column("mobile_phone", sa.String(length=32), nullable=False),
        sa.Column("dns", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("check_url", sa.String(length=500), nullable=False),
        sa.Column("request_headers", sa.Text(), nullable=True),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("success_rule", sa.Text(), nullable=True),
        sa.Column("failure_rule", sa.Text(), nullable=True),
        sa.Column("trigger_task_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_result_message", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "script_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("script_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("script_name", sa.String(length=128), nullable=False),
        sa.Column("script_dir", sa.String(length=255), nullable=False),
        sa.Column("main_file", sa.String(length=255), nullable=False),
        sa.Column("script_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "profile_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("owner_name", sa.String(length=128), nullable=False),
        sa.Column("relative_path", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("lock_owner", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "manual_repair_ticket",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("task_code", sa.String(length=64), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("risk_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_message", sa.Text(), nullable=False),
        sa.Column("repaired_by", sa.String(length=128), nullable=True),
        sa.Column("browser_artifact_dir", sa.String(length=255), nullable=True),
        sa.Column("browser_opened_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "task_run_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("check_id", sa.Integer(), nullable=True),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("log_file_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_task_run_log_run_id", "task_run_log", ["run_id"], unique=False)
    op.create_table(
        "env_check_result",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("env_check_result")
    op.drop_index("ix_task_run_log_run_id", table_name="task_run_log")
    op.drop_table("task_run_log")
    op.drop_table("manual_repair_ticket")
    op.drop_table("profile_registry")
    op.drop_table("script_registry")
    op.drop_table("health_check_config")
    op.drop_table("session_maintenance_task")
