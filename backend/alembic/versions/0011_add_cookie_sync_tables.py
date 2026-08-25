"""add cookie_sync tables

Revision ID: 0011_add_cookie_sync_tables
Revises: 0010_drop_profile_task_id
Create Date: 2026-08-25 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_add_cookie_sync_tables"
down_revision = "0010_drop_profile_task_id"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _table_exists("cookie_sync_task"):
        op.create_table(
            "cookie_sync_task",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("cookie_sync_task_code", sa.String(length=64), nullable=False),
            sa.Column("cookie_sync_task_name", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("cookie_table", sa.String(length=128), nullable=False, server_default="ods_cookie_playwright"),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("shop_name", sa.String(length=128), nullable=True),
            sa.Column("mobile_phone", sa.String(length=32), nullable=True),
            sa.Column("dns", sa.String(length=128), nullable=True),
            sa.Column("check_url", sa.String(length=500), nullable=False),
            sa.Column("http_method", sa.String(length=16), nullable=False, server_default="GET"),
            sa.Column("http_headers", sa.Text(), nullable=True),
            sa.Column("http_body", sa.Text(), nullable=True),
            sa.Column("success_rule", sa.Text(), nullable=True),
            sa.Column("failure_rule", sa.Text(), nullable=True),
            sa.Column("cron_expression", sa.String(length=128), nullable=True),
            sa.Column("check_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("30")),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("sync_wait_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("180")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
            sa.Column("last_run_status", sa.String(length=32), nullable=True),
            sa.Column("last_result_message", sa.Text(), nullable=True),
            sa.Column("last_checked_at", sa.DateTime(), nullable=True),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("cookie_sync_task_code", name="uq_cookie_sync_task_code"),
        )

    if not _table_exists("cookie_sync_mapping"):
        op.create_table(
            "cookie_sync_mapping",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("worker_id", sa.String(length=64), nullable=False),
            sa.Column("domain", sa.String(length=128), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("shop_name", sa.String(length=128), nullable=True),
            sa.Column("mobile_phone", sa.String(length=32), nullable=True),
            sa.Column("dns", sa.String(length=128), nullable=False),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("last_report_at", sa.DateTime(), nullable=True),
            sa.Column("last_report_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("worker_id", "domain", name="uq_cookie_sync_mapping_worker_domain"),
        )

    if not _table_exists("cookie_sync_job"):
        op.create_table(
            "cookie_sync_job",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("worker_id", sa.String(length=64), nullable=True),
            sa.Column("domains", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("source_task_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("task_id", name="uq_cookie_sync_job_task_id"),
        )


def downgrade() -> None:
    for name in ("cookie_sync_job", "cookie_sync_mapping", "cookie_sync_task"):
        if sa.inspect(op.get_bind()).has_table(name):
            op.drop_table(name)
