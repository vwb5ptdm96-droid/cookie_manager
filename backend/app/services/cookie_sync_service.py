from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Engine, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import create_mysql_engine
from app.core.errors import AppError
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


class CookieSyncService:
    """Cookie 扩展采集接收端服务。

    实现扩展契约的任务队列与写库逻辑：
    - 入队（POST /api/request）：定向 worker 各建一个任务，空则建广播任务
    - 轮询（GET /api/tasks）：定向匹配 + 广播任务
    - 上报（POST /api/tasks/{id}/report）：按映射写回 ods 表，定向任务以定向 worker 归属
    - 直推（POST /api/cookies）：按映射写回 ods 表
    """

    def __init__(self, engine: Engine, cookie_engine: Engine | None = None) -> None:
        self.engine = engine
        # ods 写回走云端 MySQL；无配置或测试注入时回退主库
        self.legacy_cookie_service = LegacyCookieService(
            engine=cookie_engine or (create_mysql_engine() or engine)
        )

    # ── 内部工具 ──

    @staticmethod
    def _new_task_id() -> str:
        return f"task_{uuid4().hex[:10]}"

    @staticmethod
    def _serialize_job(job: CookieSyncJob) -> dict[str, object]:
        return {
            "task_id": job.task_id,
            "worker": job.worker_id or "any",
            "domains": json.loads(job.domains or "[]"),
            "status": job.status,
        }

    # ── 入队：POST /api/request ──

    def create_request(self, domains: list[str], worker_ids: list[str]) -> dict[str, object]:
        if not domains:
            raise AppError("domains 不能为空", "EMPTY_DOMAINS")

        with Session(self.engine) as session:
            jobs: list[CookieSyncJob] = []
            if worker_ids:
                # 定向：每个 worker 建一个任务，各自只派给对应的扩展
                for wid in worker_ids:
                    job = CookieSyncJob(
                        task_id=self._new_task_id(),
                        worker_id=wid,
                        domains=json.dumps(domains, ensure_ascii=False),
                        status="pending",
                    )
                    session.add(job)
                    jobs.append(job)
            else:
                # 广播：任意采集者，谁上报按谁归属
                job = CookieSyncJob(
                    task_id=self._new_task_id(),
                    worker_id=None,
                    domains=json.dumps(domains, ensure_ascii=False),
                    status="pending",
                )
                session.add(job)
                jobs.append(job)
            session.commit()
            tasks = [self._serialize_job(j) for j in jobs]

        task_ids = [t["task_id"] for t in tasks]
        return {"task_id": task_ids[0], "task_ids": task_ids, "tasks": tasks, "status": "pending"}

    # ── 轮询：GET /api/tasks ──

    def list_pending_tasks(self, worker_id: str | None = None) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            stmt = select(CookieSyncJob).where(CookieSyncJob.status == "pending")
            if worker_id:
                stmt = stmt.where(
                    or_(CookieSyncJob.worker_id == worker_id, CookieSyncJob.worker_id.is_(None))
                )
            rows = session.execute(stmt.order_by(CookieSyncJob.created_at)).scalars().all()
        return [self._serialize_job(j) for j in rows]

    # ── 上报：POST /api/tasks/{id}/report ──

    def handle_report(
        self,
        task_id: str,
        cookies: list[dict[str, object]],
        worker_id: str | None,
    ) -> dict[str, object]:
        with Session(self.engine) as session:
            job = session.execute(
                select(CookieSyncJob).where(CookieSyncJob.task_id == task_id)
            ).scalars().first()
            if job is None:
                raise AppError(f"任务不存在: {task_id}", "TASK_NOT_FOUND", status_code=404)

            # 归属：定向任务以定向 worker 为准，否则按上报 worker_id，兜底 unknown
            attribution = job.worker_id or worker_id or "unknown"
            stored = self._write_cookies_by_mapping(session, attribution, cookies)
            job.status = "done"
            job.finished_at = beijing_now()
            session.commit()
        return {"ok": True, "stored": stored, "worker_id": attribution}

    # ── 直推：POST /api/cookies ──

    def handle_direct_upload(
        self,
        cookies: list[dict[str, object]],
        worker_id: str | None,
    ) -> dict[str, object]:
        attribution = worker_id or "unknown"
        with Session(self.engine) as session:
            stored = self._write_cookies_by_mapping(session, attribution, cookies)
            session.commit()
        return {"ok": True, "stored": stored, "worker_id": attribution}

    # ── 按映射写回 ods 表 ──

    def _write_cookies_by_mapping(self, session: Session, worker_id: str, cookies: list[dict[str, object]]) -> int:
        """按 (worker_id, cookie.domain) 查映射，映射命中则写回 ods 表，否则丢弃记 WARN。返回写入条数。"""
        by_domain: dict[str, list[dict[str, object]]] = {}
        for c in cookies:
            d = (c.get("domain") or "").strip().lower()
            if d:
                by_domain.setdefault(d, []).append(c)

        stored = 0
        for domain, cs in by_domain.items():
            # Chrome cookies 非 host-only cookie 的 domain 带前导点（.example.com），
            # 映射 domain 是操作员配的裸域名（example.com），归一化后匹配
            normalized = domain.lstrip(".")
            mapping = session.execute(
                select(CookieSyncMapping).where(
                    CookieSyncMapping.worker_id == worker_id,
                    CookieSyncMapping.domain.in_([normalized, "." + normalized]),
                )
            ).scalars().first()
            if mapping is None:
                logger.warning("无映射，丢弃 worker=%s domain=%s 的 %d 条 cookie", worker_id, normalized, len(cs))
                continue

            cookie_json = json.dumps(cs, ensure_ascii=False)
            str_cookie = "; ".join(
                f"{c['name']}={c['value']}"
                for c in cs
                if c.get("name") is not None and c.get("value") is not None
            )
            try:
                self.legacy_cookie_service.upsert_by_lookup(
                    LegacyCookieLookup(
                        channel=mapping.channel,
                        shop_name=mapping.shop_name or "",
                        mobile_phone=mapping.mobile_phone or "",
                        dns=mapping.dns,
                    ),
                    cookie_json=cookie_json,
                    str_cookie=str_cookie,
                )
            except SQLAlchemyError:
                logger.exception("写回 ods 表失败 worker=%s domain=%s", worker_id, normalized)
                raise AppError(f"写回旧表失败: {normalized}", "COOKIE_WRITE_FAILED", status_code=500) from None
            mapping.last_report_at = beijing_now()
            mapping.last_report_count += len(cs)
            stored += len(cs)
        return stored
