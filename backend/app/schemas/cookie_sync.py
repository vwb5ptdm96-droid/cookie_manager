from __future__ import annotations

from datetime import datetime

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


class CookieSyncMappingResponse(BaseModel):
    """采集映射（Spec REQ-008）。"""

    id: int
    worker_id: str
    domain: str
    channel: str
    shop_name: str | None
    mobile_phone: str | None
    dns: str
    remark: str | None
    last_report_at: datetime | None
    last_report_count: int
    created_at: datetime | None
    updated_at: datetime | None


class CookieSyncMappingCreateRequest(BaseModel):
    worker_id: str
    domain: str
    channel: str
    shop_name: str | None = None
    mobile_phone: str | None = None
    dns: str
    remark: str | None = None


class CookieSyncMappingUpdateRequest(BaseModel):
    worker_id: str | None = None
    domain: str | None = None
    channel: str | None = None
    shop_name: str | None = None
    mobile_phone: str | None = None
    dns: str | None = None
    remark: str | None = None


class CookieSyncMappingListResponse(BaseModel):
    items: list[CookieSyncMappingResponse]
