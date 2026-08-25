from __future__ import annotations

from pydantic import BaseModel


class CookieSyncRequest(BaseModel):
    """POST /api/request：采集脚本请求同步某域名某同事的 cookie。"""

    domains: list[str]
    worker_ids: list[str] = []


class CookieSyncReport(BaseModel):
    """POST /api/tasks/{id}/report：扩展上报任务读取到的 cookie。"""

    cookies: list[dict[str, object]]
    worker_id: str | None = None
    collected_at: str | None = None


class CookieSyncUpload(BaseModel):
    """POST /api/cookies：扩展定时兜底/立即同步直接推送。"""

    domains: list[str]
    cookies: list[dict[str, object]]
    worker_id: str | None = None
    collected_at: str | None = None
