from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, func
from app.core.database import Base


class CookieSyncMapping(Base):
    __tablename__ = "cookie_sync_mapping"
    __table_args__ = (
        UniqueConstraint("worker_id", "domain", name="uq_cookie_sync_mapping_worker_domain"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    worker_id: str = Column(String(64), nullable=False)
    domain: str = Column(String(128), nullable=False)
    channel: str = Column(String(32), nullable=False)
    shop_name: str | None = Column(String(128), nullable=True)
    mobile_phone: str | None = Column(String(32), nullable=True)
    dns: str = Column(String(128), nullable=False)
    remark: str | None = Column(Text, nullable=True)

    # ── 最近上报信息 ──
    last_report_at: datetime | None = Column(DateTime, nullable=True)
    last_report_count: int = Column(Integer, nullable=False, default=0)

    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
