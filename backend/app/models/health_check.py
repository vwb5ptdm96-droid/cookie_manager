from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HealthCheckConfig(Base):
    __tablename__ = "health_check_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    cookie_table: Mapped[str] = mapped_column(String(128), nullable=False, default="ods_cookie_playwright")
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mobile_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    dns: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    check_url: Mapped[str] = mapped_column(String(500), nullable=False)
    request_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    last_result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.now,
    )
