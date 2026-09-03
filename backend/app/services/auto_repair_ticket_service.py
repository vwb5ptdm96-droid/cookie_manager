"""自动排障工单数据层（Spec REQ-011 / SCOPE-019）。

职责边界：只负责自动排障工单的建单/复用、节流判定、状态回写，全部走
独立 Session（绝不借用主修复事务 session，防止提前提交 / 回滚目录锁
释放与任务状态标记）。唤起 Claude 的编排由 AgentRepairDispatcher 负责。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.auto_repair_ticket import AutoRepairTicket

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

# 工单终态（一旦进入不再参与复用与唤起）
TERMINAL_STATUSES = {"SOLVED", "NEED_HUMAN", "FAILED"}
OPEN_STATUSES = ("PENDING", "RUNNING")


def beijing_now() -> datetime:
    """返回当前北京时间（naive datetime，可直接写入 DB）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def _today_str(now: datetime | None = None) -> str:
    return (now or beijing_now()).strftime("%Y%m%d")


class AutoRepairTicketService:
    """自动排障工单的持久化操作。每个公开方法自开独立事务，互不污染。"""

    def __init__(
        self,
        engine: Engine,
        cooldown_seconds: int = 1800,
        daily_budget: int = 6,
    ) -> None:
        self.engine = engine
        # 同 (channel, shop_name) 两次唤起之间的最小间隔（秒）
        self.cooldown_seconds = cooldown_seconds
        # 同店每日可唤起上限（budget_day 维度，跨天重置）
        self.daily_budget = daily_budget

    # ── 建单 / 复用 ──

    def create_or_reuse(
        self,
        *,
        channel: str,
        shop_name: str | None = None,
        cdp_port: int = 9222,
        script_code: str | None = None,
        health_task_code: str | None = None,
        script_run_id: int | None = None,
        issue_type: str = "FAIL",
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """按 (channel, shop_name) 查未结工单：存在则复用并更新到最新上下文，
        否则新建。返回序列化工单（含 `is_new` 标记）。"""
        if issue_type not in {"FAIL", "EXCEPTION", "RISK"}:
            issue_type = "FAIL"
        ctx = {
            "cdp_port": cdp_port,
            "script_code": script_code,
            "health_task_code": health_task_code,
            "script_run_id": script_run_id,
            "issue_type": issue_type,
        }
        with Session(self.engine) as session:
            existing = self._find_open(session, channel, shop_name)
            if existing is not None:
                return self._reuse(session, existing, ctx, error_message)
            return self._create(session, channel, shop_name, cdp_port, script_code, health_task_code, script_run_id, issue_type, error_message)

    # ── 节流判定 ──

    def evaluate_dispatch(self, ticket_id: int, now: datetime | None = None) -> dict[str, Any]:
        """冷却/预算/状态检查，返回 {ok: bool, reason: str}。"""
        now = now or beijing_now()
        with Session(self.engine) as session:
            row = self._get(session, ticket_id)
            if row is None:
                return {"ok": False, "reason": f"工单不存在 id={ticket_id}"}
            if row.status in TERMINAL_STATUSES:
                return {"ok": False, "reason": f"工单已终态 ({row.status})"}
            if row.last_dispatched_at is not None:
                since = (now - row.last_dispatched_at).total_seconds()
                if since < self.cooldown_seconds:
                    remain = int(self.cooldown_seconds - since)
                    return {"ok": False, "reason": f"冷却期内 ({remain}s 后可再唤起)"}
            if row.budget_day == _today_str(now) and row.dispatch_count >= self.daily_budget:
                return {"ok": False, "reason": f"已达当日预算 ({self.daily_budget} 次/店)"}
            return {"ok": True, "reason": "ok"}

    def mark_dispatched(self, ticket_id: int, now: datetime | None = None) -> None:
        """置 RUNNING，推进当日预算计数与冷却锚点。"""
        now = now or beijing_now()
        with Session(self.engine) as session:
            row = self._get(session, ticket_id)
            if row is None:
                return
            today = _today_str(now)
            if row.budget_day != today:
                row.dispatch_count = 1
                row.budget_day = today
            else:
                row.dispatch_count = (row.dispatch_count or 0) + 1
            row.last_dispatched_at = now
            row.status = "RUNNING"
            session.commit()

    # ── 状态回写 ──

    def record_result(
        self,
        ticket_id: int,
        *,
        status: str,
        diagnosis: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """回写终态：SOLVED（排障完成关闭）/ NEED_HUMAN（转人工）/
        FAILED（唤起或执行异常，走告警）。"""
        if status not in TERMINAL_STATUSES:
            logger.warning("[AutoRepair] 非法终态 %s，忽略", status)
            return
        now = beijing_now()
        with Session(self.engine) as session:
            row = self._get(session, ticket_id)
            if row is None:
                return
            row.status = status
            row.closed_at = now
            if diagnosis is not None:
                row.diagnosis = diagnosis
            if error_message is not None:
                row.error_message = error_message
            session.commit()
            logger.info("[AutoRepair] 工单 %s → %s", row.ticket_code, status)

    # ── 查询 ──

    def list_tickets(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            stmt = select(AutoRepairTicket).order_by(AutoRepairTicket.id.desc())
            if status:
                stmt = stmt.where(AutoRepairTicket.status == status)
            rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
            return [self._serialize(row) for row in rows]

    def get_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = self._get(session, ticket_id)
            return self._serialize(row) if row is not None else None

    # ── 内部 ──

    @staticmethod
    def _find_open(session: Session, channel: str, shop_name: str | None) -> AutoRepairTicket | None:
        return session.execute(
            select(AutoRepairTicket)
            .where(
                AutoRepairTicket.channel == channel,
                AutoRepairTicket.shop_name == shop_name,
                AutoRepairTicket.status.in_(OPEN_STATUSES),
            )
            .order_by(AutoRepairTicket.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _get(session: Session, ticket_id: int) -> AutoRepairTicket | None:
        return session.get(AutoRepairTicket, ticket_id)

    def _reuse(
        self,
        session: Session,
        row: AutoRepairTicket,
        ctx: dict[str, Any],
        error_message: str | None,
    ) -> dict[str, Any]:
        # 把工单上下文更新到最新一次失败（agent 拿到的是当前现场）
        for key, value in ctx.items():
            if value is not None:
                setattr(row, key, value)
        if error_message:
            row.error_message = (
                f"{row.error_message}\n[再次失败] {error_message}"
                if row.error_message
                else f"[首次失败] {error_message}"
            )
        session.commit()
        session.refresh(row)
        result = self._serialize(row)
        result["is_new"] = False
        return result

    def _create(
        self,
        session: Session,
        channel: str,
        shop_name: str | None,
        cdp_port: int,
        script_code: str | None,
        health_task_code: str | None,
        script_run_id: int | None,
        issue_type: str,
        error_message: str | None,
    ) -> dict[str, Any]:
        from uuid import uuid4

        row = AutoRepairTicket(
            ticket_code=f"art_{uuid4().hex[:10]}",
            channel=channel,
            shop_name=shop_name,
            cdp_port=cdp_port or 9222,
            script_code=script_code,
            health_task_code=health_task_code,
            script_run_id=script_run_id,
            issue_type=issue_type,
            status="PENDING",
            error_message=error_message,
        )
        session.add(row)
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        session.refresh(row)
        result = self._serialize(row)
        result["is_new"] = True
        return result

    @staticmethod
    def _serialize(row: AutoRepairTicket) -> dict[str, Any]:
        return {
            "id": row.id,
            "ticket_code": row.ticket_code,
            "channel": row.channel,
            "shop_name": row.shop_name,
            "cdp_port": row.cdp_port,
            "script_code": row.script_code,
            "health_task_code": row.health_task_code,
            "script_run_id": row.script_run_id,
            "issue_type": row.issue_type,
            "status": row.status,
            "error_message": row.error_message,
            "diagnosis": row.diagnosis,
            "dispatch_count": row.dispatch_count,
            "budget_day": row.budget_day,
            "last_dispatched_at": row.last_dispatched_at.isoformat() if row.last_dispatched_at else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
