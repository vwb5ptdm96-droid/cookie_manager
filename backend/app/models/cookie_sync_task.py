from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint, func
from app.core.database import Base


class CookieSyncTask(Base):
    __tablename__ = "cookie_sync_task"
    __table_args__ = (
        UniqueConstraint("cookie_sync_task_code", name="uq_cookie_sync_task_code"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    cookie_sync_task_code: str = Column(String(64), nullable=False)
    cookie_sync_task_name: str = Column(String(128), nullable=False)
    enabled: bool = Column(Boolean, nullable=False, default=True)

    # ── 检测配置（复用健康检测） ──
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

    # ── 调度 ──
    cron_expression: str | None = Column(String(128), nullable=True)
    check_timeout_seconds: int = Column(Integer, nullable=False, default=30)
    retry_count: int = Column(Integer, nullable=False, default=0)

    # ── 同步设置 ──
    sync_wait_timeout_seconds: int = Column(Integer, nullable=False, default=180)

    # ── 状态 ──
    status: str = Column(String(32), nullable=False, default="PENDING")
    last_run_status: str | None = Column(String(32), nullable=True)
    last_result_message: str | None = Column(Text, nullable=True)
    last_checked_at: datetime | None = Column(DateTime, nullable=True)
    last_sync_at: datetime | None = Column(DateTime, nullable=True)
    # SYNCING 等待扩展上报的截止时间；超时后按 FAIL 处理（Spec REQ-007 / FLOW-004）
    sync_deadline_at: datetime | None = Column(DateTime, nullable=True)

    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
