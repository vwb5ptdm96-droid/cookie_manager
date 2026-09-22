"""自动排障工单数据层（Spec REQ-011 / SCOPE-019）。

职责边界：只负责自动排障工单的建单/复用、店铺维度节流判定、状态回写，全部走
独立 Session（绝不借用主修复事务 session，防止提前提交 / 回滚目录锁释放与任务
状态标记）。唤起 Claude 的编排由 AgentRepairDispatcher 负责。

节流（冷却 + 当日预算）按 `(channel, shop_name)` 店铺维度落在
AutoRepairShopState 上，与单张工单生命周期无关：上一张工单进入终态后，同店
再失败仍被节流拦下，防止单店反复失败刷爆 token。
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.auto_repair_shop_state import AutoRepairShopState
from app.models.auto_repair_ticket import AutoRepairTicket

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

# 工单终态（一旦进入不再参与复用与唤起）
TERMINAL_STATUSES = {"SOLVED", "NEED_HUMAN", "FAILED"}
OPEN_STATUSES = ("PENDING", "RUNNING")
REPAIR_ISSUE_TYPES = {"FAIL", "EXCEPTION", "RISK"}
COOKIE_ISSUE_TYPES = {"NO_MAPPING", "JOB_TIMEOUT", "RECHECK_FAIL", "DISPATCH_FAILED"}
MAX_DIAGNOSIS_CHARS = 4000
MAX_ERROR_CHARS = 2000


def beijing_now() -> datetime:
    """返回当前北京时间（naive datetime，可直接写入 DB）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def _today_str(now: datetime | None = None) -> str:
    return (now or beijing_now()).strftime("%Y%m%d")


def _norm_shop(shop_name: str | None) -> str:
    """店铺键归一：None / 空串视为同一店铺，统一存空串。"""
    return (shop_name or "").strip()


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n…(truncated {omitted} chars)"


def _sanitize(text: str | None) -> str | None:
    """统一脱敏入口（cookie/token/密码/手机号等），复用 health_task_service 实现。

    延迟 import 避免模块级循环（health_task_service → dispatcher → 本模块）。
    """
    if not text:
        return text
    try:
        from app.services.health_task_service import HealthTaskService

        return HealthTaskService._mask_sensitive(text)
    except Exception:
        return text


def purge_ticket_artifacts(runtime_root: Path, ticket_code: str) -> None:
    """删工单目录 / 日志 / 对话，不碰 scripts 与 profiles。"""
    code = (ticket_code or "").strip()
    if not code or any(ch in code for ch in ("/", "\\", "..")):
        return
    root = Path(runtime_root)
    shutil.rmtree(root / "artifacts" / code, ignore_errors=True)
    log = root / "logs" / "auto_repair" / f"{code}.log"
    if log.is_file():
        log.unlink(missing_ok=True)
    chat = root / "artifacts" / "_agent_chat" / f"{code}.jsonl"
    if chat.is_file():
        chat.unlink(missing_ok=True)


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
        # 同店每日可唤起上限（AutoRepairShopState.budget_day 维度，跨天重置）
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
        kind: str = "auto_repair",
        cookie_sync_task_code: str | None = None,
    ) -> dict[str, Any]:
        """按 (kind, channel, shop_name) 查未结工单：存在则复用并更新到最新上下文，
        否则新建。error_message 入库前统一脱敏。返回序列化工单（含 is_new）。"""
        kind = "cookie_sync" if kind == "cookie_sync" else "auto_repair"
        allowed = COOKIE_ISSUE_TYPES if kind == "cookie_sync" else REPAIR_ISSUE_TYPES
        if issue_type not in allowed:
            issue_type = "RECHECK_FAIL" if kind == "cookie_sync" else "FAIL"
        error_message = _clip(_sanitize(error_message), MAX_ERROR_CHARS)
        shop_key = _norm_shop(shop_name)
        ctx = {
            "cdp_port": cdp_port,
            "script_code": script_code,
            "health_task_code": health_task_code,
            "script_run_id": script_run_id,
            "issue_type": issue_type,
            "kind": kind,
            "cookie_sync_task_code": cookie_sync_task_code,
        }
        with Session(self.engine) as session:
            existing = self._find_open(session, channel, shop_key, kind=kind)
            if existing is not None:
                return self._reuse(session, existing, ctx, error_message)
            return self._create(
                session,
                channel,
                shop_key,
                cdp_port,
                script_code,
                health_task_code,
                script_run_id,
                issue_type,
                error_message,
                kind=kind,
                cookie_sync_task_code=cookie_sync_task_code,
            )

    # ── 店铺维度节流 ──

    def evaluate_dispatch(
        self, channel: str, shop_name: str | None, now: datetime | None = None
    ) -> dict[str, Any]:
        """冷却/预算检查（shop 维度，跨工单），返回 {ok, reason}。"""
        now = now or beijing_now()
        shop_key = _norm_shop(shop_name)
        with Session(self.engine) as session:
            state = self._get_shop_state(session, channel, shop_key)
            if state is None:
                return {"ok": True, "reason": "ok"}
            if state.last_dispatched_at is not None:
                since = (now - state.last_dispatched_at).total_seconds()
                if since < self.cooldown_seconds:
                    remain = int(self.cooldown_seconds - since)
                    return {"ok": False, "reason": f"冷却期内 ({remain}s 后可再唤起)"}
            if state.budget_day == _today_str(now) and (state.dispatch_count or 0) >= self.daily_budget:
                return {"ok": False, "reason": f"已达当日预算 ({self.daily_budget} 次/店)"}
            return {"ok": True, "reason": "ok"}

    def mark_dispatched(
        self,
        *,
        channel: str,
        shop_name: str | None,
        ticket_id: int | None = None,
        now: datetime | None = None,
    ) -> None:
        """唤起成功后记账：店铺维度推进冷却/预算 + 将关联工单置 RUNNING。

        必须在 Popen 成功之后调用，保证计次反映真实唤起。
        """
        now = now or beijing_now()
        today = _today_str(now)
        shop_key = _norm_shop(shop_name)
        with Session(self.engine) as session:
            state = self._get_shop_state(session, channel, shop_key)
            if state is None:
                state = AutoRepairShopState(channel=channel, shop_name=shop_key)
                session.add(state)
            if state.budget_day != today:
                state.dispatch_count = 1
                state.budget_day = today
            else:
                state.dispatch_count = (state.dispatch_count or 0) + 1
            state.last_dispatched_at = now

            if ticket_id is not None:
                ticket = session.get(AutoRepairTicket, ticket_id)
                if ticket is not None:
                    ticket.status = "RUNNING"
                    ticket.last_dispatched_at = now
                    ticket.budget_day = today
                    ticket.dispatch_count = state.dispatch_count  # 展示一致性（节流以 shop 维度为准）
            try:
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise

    # ── 状态回写 ──

    def record_result(
        self,
        ticket_id: int,
        *,
        status: str,
        diagnosis: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """回写终态：SOLVED / NEED_HUMAN / FAILED，落库前统一脱敏。"""
        if status not in TERMINAL_STATUSES:
            logger.warning("[AutoRepair] 非法终态 %s，忽略", status)
            return
        diagnosis = _clip(_sanitize(diagnosis), MAX_DIAGNOSIS_CHARS)
        error_message = _clip(_sanitize(error_message), MAX_ERROR_CHARS)
        now = beijing_now()
        with Session(self.engine) as session:
            row = session.get(AutoRepairTicket, ticket_id)
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
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            stmt = select(AutoRepairTicket).order_by(AutoRepairTicket.id.desc())
            if status:
                stmt = stmt.where(AutoRepairTicket.status == status)
            if kind:
                stmt = stmt.where(AutoRepairTicket.kind == kind)
            rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
            return [self._serialize(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(AutoRepairTicket.status, func.count())
                .group_by(AutoRepairTicket.status)
            ).all()
        counts = {str(status): int(n) for status, n in rows}
        counts["running"] = counts.get("RUNNING", 0)
        counts["pending"] = counts.get("PENDING", 0)
        counts["total"] = sum(int(v) for k, v in counts.items() if k not in {"running", "pending", "total"})
        return counts

    def get_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(AutoRepairTicket, ticket_id)
            return self._serialize(row) if row is not None else None

    def delete_ticket(self, ticket_id: int) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.get(AutoRepairTicket, ticket_id)
            if row is None:
                raise AppError("自动排障工单不存在", "AUTO_REPAIR_TICKET_NOT_FOUND", status_code=404)
            if row.status == "RUNNING":
                raise AppError("处理中的工单不能删", "TICKET_DELETE_RUNNING", status_code=409)
            data = self._serialize(row)
            session.delete(row)
            session.commit()
            return data

    def delete_closed_tickets(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(AutoRepairTicket).where(AutoRepairTicket.status.in_(tuple(TERMINAL_STATUSES)))
            ).scalars().all()
            deleted = [self._serialize(row) for row in rows]
            for row in rows:
                session.delete(row)
            session.commit()
            return deleted

    def list_stale_running(self, older_than: datetime) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(AutoRepairTicket).where(
                    AutoRepairTicket.status == "RUNNING",
                    AutoRepairTicket.last_dispatched_at.is_not(None),
                    AutoRepairTicket.last_dispatched_at < older_than,
                )
            ).scalars().all()
            return [self._serialize(row) for row in rows]

    def list_stale_pending(self, older_than: datetime) -> list[dict[str, Any]]:
        from app.core.time_utils import db_naive_as_beijing

        with Session(self.engine) as session:
            rows = session.execute(
                select(AutoRepairTicket).where(AutoRepairTicket.status == "PENDING")
            ).scalars().all()
            stale = []
            for row in rows:
                created = db_naive_as_beijing(row.created_at, now=older_than + timedelta(seconds=1))
                if created is not None and created < older_than:
                    stale.append(self._serialize(row))
            return stale

    # ── 内部 ──

    @staticmethod
    def _find_open(session: Session, channel: str, shop_key: str, *, kind: str = "auto_repair") -> AutoRepairTicket | None:
        return session.execute(
            select(AutoRepairTicket)
            .where(
                AutoRepairTicket.channel == channel,
                AutoRepairTicket.shop_name == shop_key,
                AutoRepairTicket.kind == kind,
                AutoRepairTicket.status.in_(OPEN_STATUSES),
            )
            .order_by(AutoRepairTicket.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _get_shop_state(
        session: Session, channel: str, shop_key: str
    ) -> AutoRepairShopState | None:
        return session.execute(
            select(AutoRepairShopState).where(
                AutoRepairShopState.channel == channel,
                AutoRepairShopState.shop_name == shop_key,
            )
        ).scalar_one_or_none()

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
            combined = (
                f"{row.error_message}\n[再次失败] {error_message}"
                if row.error_message
                else f"[首次失败] {error_message}"
            )
            row.error_message = _clip(combined, MAX_ERROR_CHARS)
        session.commit()
        session.refresh(row)
        result = self._serialize(row)
        result["is_new"] = False
        return result

    def _create(
        self,
        session: Session,
        channel: str,
        shop_key: str,
        cdp_port: int,
        script_code: str | None,
        health_task_code: str | None,
        script_run_id: int | None,
        issue_type: str,
        error_message: str | None,
        *,
        kind: str = "auto_repair",
        cookie_sync_task_code: str | None = None,
    ) -> dict[str, Any]:
        prefix = "cst_" if kind == "cookie_sync" else "art_"
        row = AutoRepairTicket(
            ticket_code=f"{prefix}{uuid4().hex[:10]}",
            channel=channel,
            shop_name=shop_key,
            cdp_port=cdp_port or 9222,
            script_code=script_code,
            health_task_code=health_task_code,
            script_run_id=script_run_id,
            issue_type=issue_type,
            kind=kind,
            cookie_sync_task_code=cookie_sync_task_code,
            status="PENDING",
            error_message=error_message,
            created_at=beijing_now(),
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
            "kind": getattr(row, "kind", None) or "auto_repair",
            "cookie_sync_task_code": getattr(row, "cookie_sync_task_code", None),
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
