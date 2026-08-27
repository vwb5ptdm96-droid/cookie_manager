from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory, require_cookie_sync_key
from app.schemas.cookie_sync import (
    CookieSyncManualUpload,
    CookieSyncReport,
    CookieSyncRequest,
    CookieSyncUpload,
)
from app.services.cookie_sync_service import CookieSyncService

router = APIRouter(tags=["cookie-sync"])


def build_cookie_sync_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> CookieSyncService:
    engine: Engine = session_factory.kw["bind"]
    return CookieSyncService(engine=engine)


@router.get("/ping")
def ping() -> dict[str, str]:
    """扩展测试连接用，无鉴权。"""
    return {"status": "ok"}


@router.post("/request")
def request_sync(
    payload: CookieSyncRequest,
    service: CookieSyncService = Depends(build_cookie_sync_service),
    _: None = Depends(require_cookie_sync_key),
) -> dict[str, object]:
    """采集脚本请求同步某域名某同事的 cookie。"""
    return service.create_request(domains=payload.domains, worker_ids=payload.worker_ids)


@router.get("/tasks")
def get_tasks(
    worker_id: str | None = None,
    service: CookieSyncService = Depends(build_cookie_sync_service),
    _: None = Depends(require_cookie_sync_key),
) -> dict[str, object]:
    """扩展轮询：返回派给该采集者的待处理任务。"""
    return {"tasks": service.list_pending_tasks(worker_id)}


@router.post("/tasks/{task_id}/report")
def report_task(
    task_id: str,
    payload: CookieSyncReport,
    service: CookieSyncService = Depends(build_cookie_sync_service),
    _: None = Depends(require_cookie_sync_key),
) -> dict[str, object]:
    """扩展上报读取到的 cookie，按映射写回旧表。"""
    return service.handle_report(
        task_id=task_id,
        cookies=payload.cookies,
        worker_id=payload.worker_id,
    )


@router.post("/cookies")
def upload_cookies(
    payload: CookieSyncUpload,
    service: CookieSyncService = Depends(build_cookie_sync_service),
    _: None = Depends(require_cookie_sync_key),
) -> dict[str, object]:
    """扩展定时兜底/立即同步直接推送 cookie。"""
    return service.handle_direct_upload(
        cookies=payload.cookies,
        worker_id=payload.worker_id,
    )


@router.post("/cookies/manual")
def upload_manual(
    payload: CookieSyncManualUpload,
    service: CookieSyncService = Depends(build_cookie_sync_service),
    _: None = Depends(require_cookie_sync_key),
) -> dict[str, object]:
    """手动上报扩展「Cookie 一键上报」：按四字段 upsert 写回旧表，不经映射表、无 worker 归属。"""
    return service.handle_manual_upload(
        channel=payload.channel,
        shop_name=payload.shop_name,
        mobile_phone=payload.mobile_phone,
        dns=payload.dns,
        cookies=payload.cookies,
    )
