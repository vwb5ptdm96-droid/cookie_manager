from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ManualRepairTicket(Base):
    __tablename__ = "manual_repair_ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_code: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False)
    health_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_task_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    script_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    script_run_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    directory_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_type: Mapped[str] = mapped_column(String(64), nullable=False, default="RISK")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    risk_message: Mapped[str] = mapped_column(Text, nullable=False)
    repaired_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    browser_artifact_dir: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.now,
    )
