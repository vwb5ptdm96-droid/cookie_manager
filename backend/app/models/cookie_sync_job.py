from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from app.core.database import Base


class CookieSyncJob(Base):
    __tablename__ = "cookie_sync_job"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    # 给扩展的任务标识（task_xxx）
    task_id: str = Column(String(64), unique=True, nullable=False)
    # 定向 worker_id；空/None 为广播任务
    worker_id: str | None = Column(String(64), nullable=True)
    # 要采集的域名，JSON 数组字符串
    domains: str = Column(Text, nullable=False, default="[]")
    # pending / done
    status: str = Column(String(32), nullable=False, default="pending")
    # 关联 cookie_sync_task.id（采集任务发起时为 null）
    source_task_id: int | None = Column(Integer, nullable=True)

    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    finished_at: datetime | None = Column(DateTime, nullable=True)
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
