"""值班早报：只读聚合，不调模型。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from app.models.auto_repair_ticket import AutoRepairTicket
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_task import CookieSyncTask
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.script_run import ScriptRun
from app.services.auto_repair_ticket_service import beijing_now


def build_ops_summary(engine: Engine, *, now: datetime | None = None) -> dict[str, Any]:
    clock = now or beijing_now()
    today = clock.replace(hour=0, minute=0, second=0, microsecond=0)
    attention: list[dict[str, Any]] = []

    with Session(engine) as session:
        health_enabled = int(
            session.execute(select(func.count()).select_from(HealthTask).where(HealthTask.enabled.is_(True))).scalar()
            or 0
        )
        health_fail = int(
            session.execute(
                select(func.count())
                .select_from(HealthTask)
                .where(HealthTask.enabled.is_(True), HealthTask.last_run_status.in_(("FAIL", "FAILED", "RISK")))
            ).scalar()
            or 0
        )
        cookie_enabled = int(
            session.execute(
                select(func.count()).select_from(CookieSyncTask).where(CookieSyncTask.enabled.is_(True))
            ).scalar()
            or 0
        )
        cookie_fail = int(
            session.execute(
                select(func.count())
                .select_from(CookieSyncTask)
                .where(
                    CookieSyncTask.enabled.is_(True),
                    CookieSyncTask.last_run_status.in_(("FAIL", "FAILED")),
                )
            ).scalar()
            or 0
        )
        cookie_syncing = int(
            session.execute(
                select(func.count()).select_from(CookieSyncTask).where(CookieSyncTask.status == "SYNCING")
            ).scalar()
            or 0
        )
        jobs_pending = int(
            session.execute(
                select(func.count()).select_from(CookieSyncJob).where(CookieSyncJob.status == "pending")
            ).scalar()
            or 0
        )
        runs_running = int(
            session.execute(select(func.count()).select_from(ScriptRun).where(ScriptRun.status == "RUNNING")).scalar()
            or 0
        )
        runs_risk = int(
            session.execute(select(func.count()).select_from(ScriptRun).where(ScriptRun.status == "RISK")).scalar()
            or 0
        )
        locked = int(
            session.execute(
                select(func.count()).select_from(ProfileRegistry).where(ProfileRegistry.is_locked.is_(True))
            ).scalar()
            or 0
        )
        ticket_counts = {
            str(status): int(n)
            for status, n in session.execute(
                select(AutoRepairTicket.status, func.count()).group_by(AutoRepairTicket.status)
            ).all()
        }
        solved_today = int(
            session.execute(
                select(func.count())
                .select_from(AutoRepairTicket)
                .where(AutoRepairTicket.status == "SOLVED", AutoRepairTicket.closed_at >= today)
            ).scalar()
            or 0
        )

        for row in session.execute(
            select(AutoRepairTicket)
            .where(AutoRepairTicket.status.in_(("NEED_HUMAN", "FAILED", "RUNNING", "PENDING")))
            .order_by(AutoRepairTicket.id.desc())
            .limit(5)
        ).scalars():
            shop = row.shop_name or row.ticket_code
            attention.append(
                {
                    "title": shop,
                    "reason": f"排障 {row.status}",
                    "path": "/auto-repair-tickets",
                    "query": {"ticket": str(row.id)},
                }
            )

        if len(attention) < 5:
            for row in session.execute(
                select(HealthTask)
                .where(HealthTask.enabled.is_(True), HealthTask.last_run_status.in_(("FAIL", "FAILED", "RISK")))
                .order_by(HealthTask.updated_at.desc())
                .limit(5)
            ).scalars():
                if len(attention) >= 5:
                    break
                keyword = row.shop_name or row.health_task_name
                attention.append(
                    {
                        "title": keyword,
                        "reason": f"健康检测 {row.last_run_status}",
                        "path": "/health-tasks",
                        "query": {"keyword": keyword},
                    }
                )

        if len(attention) < 5:
            for row in session.execute(
                select(CookieSyncTask)
                .where(
                    CookieSyncTask.enabled.is_(True),
                    or_(
                        CookieSyncTask.status == "SYNCING",
                        CookieSyncTask.last_run_status.in_(("FAIL", "FAILED")),
                    ),
                )
                .order_by(CookieSyncTask.updated_at.desc())
                .limit(5)
            ).scalars():
                if len(attention) >= 5:
                    break
                keyword = row.shop_name or row.cookie_sync_task_name
                attention.append(
                    {
                        "title": keyword,
                        "reason": f"采集 {row.status}/{row.last_run_status or '-'}",
                        "path": "/cookie-sync-tasks",
                        "query": {"keyword": keyword},
                    }
                )

    window_start = (clock - timedelta(hours=14)).isoformat(timespec="minutes")
    return {
        "as_of": clock.isoformat(timespec="seconds"),
        "window_start": window_start,
        "health": {"enabled": health_enabled, "fail": health_fail},
        "cookie_sync": {
            "enabled": cookie_enabled,
            "fail": cookie_fail,
            "syncing": cookie_syncing,
            "jobs_pending": jobs_pending,
        },
        "script_runs": {"running": runs_running, "risk": runs_risk},
        "profiles": {"locked": locked},
        "agent": {
            "running": int(ticket_counts.get("RUNNING") or 0),
            "pending": int(ticket_counts.get("PENDING") or 0),
            "solved_today": solved_today,
            "need_human": int(ticket_counts.get("NEED_HUMAN") or 0),
            "failed": int(ticket_counts.get("FAILED") or 0),
        },
        "attention": attention[:5],
    }
