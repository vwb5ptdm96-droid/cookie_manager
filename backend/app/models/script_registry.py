from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScriptRegistry(Base):
    __tablename__ = "script_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    script_name: Mapped[str] = mapped_column(String(128), nullable=False)
    script_dir: Mapped[str] = mapped_column(String(255), nullable=False)
    main_file: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    script_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_run_mode: Mapped[str | None] = mapped_column(String(16), nullable=True, default="HEADLESS")
    default_cdp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_pause: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_cancel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.now,
    )
