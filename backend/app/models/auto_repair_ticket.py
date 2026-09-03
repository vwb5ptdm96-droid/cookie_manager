from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.core.database import Base


class AutoRepairTicket(Base):
    """自动排障工单（Spec REQ-011 / SCOPE-019）。

    修复脚本运行 FAIL/异常/RISK 收尾时自动创建，唤起本机 Claude Code
    排障后回写终态：SOLVED（关闭）或 NEED_HUMAN（关端口 + 飞书转人工）。
    独立于已废弃的人工维修工单（ManualRepairTicket），不与之共用表。
    """

    __tablename__ = "auto_repair_ticket"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticket_code: str = Column(String(64), unique=True, nullable=False)

    # ── 业务定位（取自已执行 HealthTask，禁止取 ScriptRegistry.platform/script_name）──
    channel: str = Column(String(32), nullable=False)
    shop_name: str | None = Column(String(128), nullable=True)
    cdp_port: int = Column(Integer, nullable=False, default=9222)

    # ── 关联上下文 ──
    script_code: str | None = Column(String(64), nullable=True)
    health_task_code: str | None = Column(String(64), nullable=True)
    script_run_id: int | None = Column(Integer, nullable=True)

    # ── 工单流转 ──
    # issue_type: FAIL / EXCEPTION / RISK
    issue_type: str = Column(String(16), nullable=False, default="FAIL")
    # status: PENDING / RUNNING / SOLVED / NEED_HUMAN / FAILED
    status: str = Column(String(16), nullable=False, default="PENDING")
    error_message: str | None = Column(Text, nullable=True)
    # diagnosis: 排障 agent 结论（阻挡原因/处理动作/修复结果）
    diagnosis: str | None = Column(Text, nullable=True)

    # ── 唤起节流（落库，后端重启不失效）──
    dispatch_count: int = Column(Integer, nullable=False, default=0)
    # budget_day: YYYYMMDD 归属日，跨天重置 dispatch_count
    budget_day: str | None = Column(String(8), nullable=True)
    last_dispatched_at: datetime | None = Column(DateTime, nullable=True)

    closed_at: datetime | None = Column(DateTime, nullable=True)
    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=datetime.now)
