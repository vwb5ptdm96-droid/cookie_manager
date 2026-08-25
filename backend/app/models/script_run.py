from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from app.core.database import Base


class ScriptRun(Base):
    __tablename__ = "script_run"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    run_id: str = Column(String(64), unique=True, nullable=False)

    # 关联
    health_task_id: int | None = Column(Integer, nullable=True)
    health_task_code: str | None = Column(String(64), nullable=True)
    script_id: int = Column(Integer, nullable=False)
    script_code: str = Column(String(64), nullable=False)
    directory_id: int | None = Column(Integer, nullable=True)
    directory_key: str | None = Column(String(64), nullable=True)

    # 运行配置
    run_mode: str = Column(String(16), nullable=False, default="HEADLESS")
    script_config: str | None = Column(Text, nullable=True)
    timeout_seconds: int = Column(Integer, nullable=False, default=600)

    # 运行时
    status: str = Column(String(32), nullable=False, default="PENDING")
    # PENDING / RUNNING / PAUSED / CANCELING / CANCELED / SUCCESS / FAIL / RISK
    pid: int | None = Column(Integer, nullable=True)
    start_time: datetime | None = Column(DateTime, nullable=True)
    end_time: datetime | None = Column(DateTime, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)

    # 产物
    artifact_dir: str | None = Column(String(255), nullable=True)
    log_file: str | None = Column(String(255), nullable=True)
    stdout_file: str | None = Column(String(255), nullable=True)
    stderr_file: str | None = Column(String(255), nullable=True)
    result_json: str | None = Column(Text, nullable=True)
    error_message: str | None = Column(Text, nullable=True)
    exit_code: int | None = Column(Integer, nullable=True)

    # 控制
    control_file: str | None = Column(String(255), nullable=True)

    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
