from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from app.core.database import Base


class HealthTask(Base):
    __tablename__ = "health_task"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    health_task_code: str = Column(String(64), unique=True, nullable=False)
    health_task_name: str = Column(String(128), nullable=False)
    enabled: bool = Column(Boolean, nullable=False, default=True)

    # ── 1. 检测配置 ──
    cookie_table: str = Column(String(128), nullable=False, default="ods_cookie_playwright")
    channel: str = Column(String(32), nullable=False)
    shop_name: str | None = Column(String(128), nullable=True)
    mobile_phone: str | None = Column(String(32), nullable=True)
    dns: str | None = Column(String(128), nullable=True)
    check_url: str = Column(String(500), nullable=False)
    http_method: str = Column(String(16), nullable=False, default="GET")
    http_headers: str | None = Column(Text, nullable=True)
    http_body: str | None = Column(Text, nullable=True)
    success_rule: str | None = Column(Text, nullable=True)
    failure_rule: str | None = Column(Text, nullable=True)

    # ── 2. 高级调度配置 ──
    cron_expression: str | None = Column(String(128), nullable=True)
    check_timeout_seconds: int = Column(Integer, nullable=False, default=30)
    retry_count: int = Column(Integer, nullable=False, default=0)
    last_checked_at: datetime | None = Column(DateTime, nullable=True)
    next_run_at: datetime | None = Column(DateTime, nullable=True)

    # ── 3. 失败修复配置 ──
    auto_repair_enabled: bool = Column(Boolean, nullable=False, default=False)
    repair_cron_expression: str | None = Column(String(128), nullable=True)
    repair_script_id: int | None = Column(Integer, nullable=True)
    repair_directory_id: int | None = Column(Integer, nullable=True)
    repair_run_mode: str | None = Column(String(16), nullable=True)
    repair_script_config: str | None = Column(Text, nullable=True)
    repair_timeout_seconds: int = Column(Integer, nullable=False, default=600)

    # ── 状态 ──
    status: str = Column(String(32), nullable=False, default="PENDING")
    last_run_status: str | None = Column(String(32), nullable=True)
    last_result_message: str | None = Column(Text, nullable=True)
    last_repaired_at: datetime | None = Column(DateTime, nullable=True)
    last_repair_run_id: str | None = Column(String(64), nullable=True)

    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
