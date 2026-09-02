from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models.health_task import HealthTask

logger = logging.getLogger(__name__)


class HealthTaskScheduler:
    """基于 HealthTask cron_expression 的调度器，每分钟扫描一次待执行任务。"""

    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        self.scheduler = None

    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler

        if self.scheduler is not None:
            return

        scheduler = BackgroundScheduler()
        scheduler.add_job(self._scan, "interval", minutes=1, id="health-task-scan")
        scheduler.start()
        self.scheduler = scheduler
        logger.info("HealthTaskScheduler started, scanning every 1 minute")

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
            logger.info("HealthTaskScheduler stopped")

    def _scan(self) -> None:
        """扫描所有启用的 HealthTask，执行到期的检测。"""
        from app.services.health_task_service import HealthTaskService

        now = datetime.now()
        service = HealthTaskService(engine=self.engine, runtime_root=self.runtime_root)

        # 回收超时未收尾的僵死执行实例并同步释放目录锁（防僵尸 run / 孤锁积压）
        try:
            service.reap_stale_runs()
        except Exception:
            logger.exception("调度回收僵死执行实例异常")

        with Session(self.engine) as session:
            tasks = session.execute(
                select(HealthTask).where(HealthTask.enabled.is_(True))
            ).scalars().all()

        for task in tasks:
            # ── 检测调度 ──
            # 有 cron 表达式才走调度；无 cron（=手动）仅手动触发，调度器跳过（ASM-003）
            if task.cron_expression:
                if self._match_cron(task.cron_expression.strip(), now):
                    try:
                        service.execute_check(task.health_task_code)
                    except Exception as exc:
                        logger.exception("调度检测失败 [%s]: %s", task.health_task_code, exc)

            # ── 修复调度（独立 cron，不管检测结果）──
            if task.repair_cron_expression and task.repair_script_id:
                if self._match_cron(task.repair_cron_expression.strip(), now):
                    try:
                        service.execute_scheduled_repair(task.health_task_code)
                    except Exception as exc:
                        logger.exception("调度定时修复失败 [%s]: %s", task.health_task_code, exc)

        # Cookie 采集任务扫描（Phase 9：定时检测 + SYNCING 复检/超时收尾）
        self._scan_cookie_sync_tasks()

    def _scan_cookie_sync_tasks(self) -> None:
        """扫描 Cookie 采集任务：cron 到期触发检测；SYNCING 任务按上报完成复检 / 超时 FAIL。

        独立于健康检测任务调度，两者互不耦合（Spec OUT-010）。
        """
        from app.models.cookie_sync_job import CookieSyncJob
        from app.models.cookie_sync_task import CookieSyncTask
        from app.services.cookie_sync_task_service import (
            CookieSyncTaskService,
            beijing_now,
        )

        now = datetime.now()
        service = CookieSyncTaskService(engine=self.engine, runtime_root=self.runtime_root)

        with Session(self.engine) as session:
            sync_tasks = session.execute(
                select(CookieSyncTask).where(CookieSyncTask.enabled.is_(True))
            ).scalars().all()

        for task in sync_tasks:
            # ── 定时检测 ──
            # 有 cron 表达式才走调度；无 cron（=手动）仅手动触发，调度器跳过（ASM-003）。
            # SYNCING（等待扩展采集上报）的任务不重复触发检测，避免重复下发采集（由下方收尾逻辑复检/超时处理）。
            if task.cron_expression and task.status != "SYNCING":
                if self._match_cron(task.cron_expression.strip(), now):
                    try:
                        service.execute_check(task.cookie_sync_task_code)
                    except Exception as exc:
                        logger.exception("采集任务调度检测失败 [%s]: %s", task.cookie_sync_task_code, exc)

        # ── SYNCING 收尾：上报完成 → 复检；超时 → FAIL ──
        with Session(self.engine) as session:
            syncing_rows = session.execute(
                select(CookieSyncTask).where(CookieSyncTask.status == "SYNCING")
            ).scalars().all()
            jobs_by_source: dict[int, list[CookieSyncJob]] = {}
            for row in syncing_rows:
                jobs = session.execute(
                    select(CookieSyncJob)
                    .where(CookieSyncJob.source_task_id == row.id)
                    .order_by(CookieSyncJob.created_at.desc())
                ).scalars().all()
                jobs_by_source[row.id] = jobs

        for row in syncing_rows:
            jobs = jobs_by_source.get(row.id, [])
            # MAJOR-4：优先取任一已完成的 job 复检，避免新建 pending job 盖过旧 done job 导致卡死
            done_job = next((j for j in jobs if j.status == "done"), None)
            if done_job is not None:
                try:
                    service.recheck_after_sync(row.id)
                except Exception as exc:
                    logger.exception("采集任务复检失败 [%s]: %s", row.cookie_sync_task_code, exc)
            elif row.sync_deadline_at is not None and beijing_now() > row.sync_deadline_at:
                try:
                    service.fail_on_timeout(row.id)
                except Exception as exc:
                    logger.exception("采集任务超时处理失败 [%s]: %s", row.cookie_sync_task_code, exc)

    # ── 简易 cron 匹配（标准 5 位表达式）──

    @staticmethod
    def _match_cron(expression: str, dt: datetime) -> bool:
        parts = expression.split()
        if len(parts) != 5:
            logger.warning("不支持的 cron 表达式: %s", expression)
            return False

        minute, hour, day, month, day_of_week = parts

        if not HealthTaskScheduler._cron_field_match(minute, dt.minute, 0, 59):
            return False
        if not HealthTaskScheduler._cron_field_match(hour, dt.hour, 0, 23):
            return False
        if not HealthTaskScheduler._cron_field_match(day, dt.day, 1, 31):
            return False
        if not HealthTaskScheduler._cron_field_match(month, dt.month, 1, 12):
            return False
        # Python weekday: Monday=0, Sunday=6; cron: Sunday=0, Saturday=6
        cron_dow = (dt.weekday() + 1) % 7
        if not HealthTaskScheduler._cron_field_match(day_of_week, cron_dow, 0, 6):
            return False

        return True

    @staticmethod
    def _cron_field_match(pattern: str, value: int, _min: int, _max: int) -> bool:
        if pattern == "*":
            return True
        if "/" in pattern:
            # */5 → every 5
            parts = pattern.split("/")
            base = parts[0]
            step = int(parts[1])
            if base == "*":
                return value % step == 0
            # 5/10 → from 5, every 10
            start = int(base)
            return value >= start and (value - start) % step == 0
        if "," in pattern:
            return value in [int(p) for p in pattern.split(",")]
        if "-" in pattern:
            low, high = pattern.split("-")
            return int(low) <= value <= int(high)
        return int(pattern) == value


