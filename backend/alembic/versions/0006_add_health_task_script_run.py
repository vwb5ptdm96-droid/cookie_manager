"""add health_task, script_run, run-control fields

Revision ID: 0006_add_health_task_script_run
Revises: 0005_add_script_profile_key
Create Date: 2026-07-01 20:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_add_health_task_script_run"
down_revision = "0005_add_script_profile_key"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # ── 1. 创建 health_task 表 ──
    if not _has_table("health_task"):
        op.create_table(
            "health_task",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("health_task_code", sa.String(64), unique=True, nullable=False),
            sa.Column("health_task_name", sa.String(128), nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),

            # 检测配置
            sa.Column("cookie_table", sa.String(128), nullable=False, server_default="ods_cookie_playwright"),
            sa.Column("channel", sa.String(32), nullable=False),
            sa.Column("shop_name", sa.String(128), nullable=True),
            sa.Column("mobile_phone", sa.String(32), nullable=True),
            sa.Column("dns", sa.String(128), nullable=True),
            sa.Column("check_url", sa.String(500), nullable=False),
            sa.Column("http_method", sa.String(16), nullable=False, server_default="GET"),
            sa.Column("http_headers", sa.Text, nullable=True),
            sa.Column("http_body", sa.Text, nullable=True),
            sa.Column("success_rule", sa.Text, nullable=True),
            sa.Column("failure_rule", sa.Text, nullable=True),

            # 高级调度
            sa.Column("cron_expression", sa.String(128), nullable=True),
            sa.Column("check_timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("30")),
            sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
            sa.Column("last_checked_at", sa.DateTime, nullable=True),
            sa.Column("next_run_at", sa.DateTime, nullable=True),

            # 失败修复
            sa.Column("auto_repair_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("repair_script_id", sa.Integer, nullable=True),
            sa.Column("repair_directory_id", sa.Integer, nullable=True),
            sa.Column("repair_run_mode", sa.String(16), nullable=True),
            sa.Column("repair_script_config", sa.Text, nullable=True),
            sa.Column("repair_timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("600")),

            # 状态
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("last_run_status", sa.String(32), nullable=True),
            sa.Column("last_result_message", sa.Text, nullable=True),
            sa.Column("last_repaired_at", sa.DateTime, nullable=True),
            sa.Column("last_repair_run_id", sa.String(64), nullable=True),

            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    # ── 2. 创建 script_run 表 ──
    if not _has_table("script_run"):
        op.create_table(
            "script_run",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(64), unique=True, nullable=False),

            # 关联
            sa.Column("health_task_id", sa.Integer, nullable=True),
            sa.Column("health_task_code", sa.String(64), nullable=True),
            sa.Column("script_id", sa.Integer, nullable=False),
            sa.Column("script_code", sa.String(64), nullable=False),
            sa.Column("directory_id", sa.Integer, nullable=True),
            sa.Column("directory_key", sa.String(64), nullable=True),

            # 运行配置
            sa.Column("run_mode", sa.String(16), nullable=False, server_default="HEADLESS"),
            sa.Column("script_config", sa.Text, nullable=True),
            sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("600")),

            # 运行时
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("pid", sa.Integer, nullable=True),
            sa.Column("start_time", sa.DateTime, nullable=True),
            sa.Column("end_time", sa.DateTime, nullable=True),
            sa.Column("duration_ms", sa.Integer, nullable=True),

            # 产物
            sa.Column("artifact_dir", sa.String(255), nullable=True),
            sa.Column("log_file", sa.String(255), nullable=True),
            sa.Column("stdout_file", sa.String(255), nullable=True),
            sa.Column("stderr_file", sa.String(255), nullable=True),
            sa.Column("result_json", sa.Text, nullable=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("exit_code", sa.Integer, nullable=True),

            # 控制
            sa.Column("control_file", sa.String(255), nullable=True),

            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    # ── 3. script_registry 增加运行控制字段 ──
    if not _has_column("script_registry", "default_run_mode"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.add_column(sa.Column("default_run_mode", sa.String(16), nullable=True))
            batch_op.add_column(sa.Column("supports_pause", sa.Boolean, nullable=False, server_default=sa.text("0")))
            batch_op.add_column(sa.Column("supports_cancel", sa.Boolean, nullable=False, server_default=sa.text("1")))
            batch_op.add_column(sa.Column("default_timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("600")))

    # ── 4. profile_registry 增加锁字段 ──
    if not _has_column("profile_registry", "lock_run_id"):
        with op.batch_alter_table("profile_registry") as batch_op:
            batch_op.add_column(sa.Column("lock_run_id", sa.String(64), nullable=True))
            batch_op.add_column(sa.Column("locked_at", sa.DateTime, nullable=True))

    # ── 5. manual_repair_ticket 增加关联字段 ──
    if not _has_column("manual_repair_ticket", "health_task_id"):
        with op.batch_alter_table("manual_repair_ticket") as batch_op:
            batch_op.add_column(sa.Column("health_task_id", sa.Integer, nullable=True))
            batch_op.add_column(sa.Column("health_task_code", sa.String(64), nullable=True))
            batch_op.add_column(sa.Column("script_run_id", sa.Integer, nullable=True))
            batch_op.add_column(sa.Column("script_run_code", sa.String(64), nullable=True))
            batch_op.add_column(sa.Column("directory_key", sa.String(64), nullable=True))


def downgrade() -> None:
    # 逆序撤销
    if _has_column("manual_repair_ticket", "health_task_id"):
        with op.batch_alter_table("manual_repair_ticket") as batch_op:
            batch_op.drop_column("health_task_id")
            batch_op.drop_column("health_task_code")
            batch_op.drop_column("script_run_id")
            batch_op.drop_column("script_run_code")
            batch_op.drop_column("directory_key")

    if _has_column("profile_registry", "lock_run_id"):
        with op.batch_alter_table("profile_registry") as batch_op:
            batch_op.drop_column("lock_run_id")
            batch_op.drop_column("locked_at")

    if _has_column("script_registry", "default_run_mode"):
        with op.batch_alter_table("script_registry") as batch_op:
            batch_op.drop_column("default_run_mode")
            batch_op.drop_column("supports_pause")
            batch_op.drop_column("supports_cancel")
            batch_op.drop_column("default_timeout_seconds")

    if _has_table("script_run"):
        op.drop_table("script_run")

    if _has_table("health_task"):
        op.drop_table("health_task")
