from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class AutoRepairShopState(Base):
    """店铺维度的自动排障节流状态（Spec REQ-011：冷却/预算按 (channel, shop) 全局计）。

    冷却与当日预算按店铺全局生效，与工单生命周期无关：
    上一张工单无论 SOLVED/NEED_HUMAN/FAILED，只要该店仍频繁失败，新的失败
    建单前都会先查这里 —— 防单店反复失败刷爆 token。

    注：(channel, shop_name) 单行由 service 查后插保证，DB 不建唯一约束
    （SQLite 迁移不支持 ALTER 加约束；后端单进程 + 修复串行，竞态可忽略）。
    """

    __tablename__ = "auto_repair_shop_state"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    channel: str = Column(String(32), nullable=False)
    # shop_name 归一存 ""（None/空串视为同一店铺键）
    shop_name: str = Column(String(128), nullable=False, default="")

    last_dispatched_at: datetime | None = Column(DateTime, nullable=True)
    # budget_day: YYYYMMDD 归属日，跨天重置 dispatch_count
    budget_day: str | None = Column(String(8), nullable=True)
    dispatch_count: int = Column(Integer, nullable=False, default=0)

    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
