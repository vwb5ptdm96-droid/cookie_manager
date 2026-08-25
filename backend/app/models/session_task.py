from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessionMaintenanceTask(Base):
    __tablename__ = "session_maintenance_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    mobile_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    account_alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    related_dns: Mapped[str] = mapped_column(Text, nullable=False)
    script_code: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    schedule_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    script_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INIT")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_artifact_dir: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.now,
    )
