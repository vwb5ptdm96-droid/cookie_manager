from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CookieSyncTaskResponse(BaseModel):
    id: int
    cookie_sync_task_code: str
    cookie_sync_task_name: str
    enabled: bool

    # 检测配置（复用健康检测）
    cookie_table: str
    channel: str
    shop_name: str | None
    mobile_phone: str | None
    dns: str | None
    check_url: str
    http_method: str
    http_headers: str | None
    http_body: str | None
    success_rule: str | None
    failure_rule: str | None

    # 调度
    cron_expression: str | None
    check_timeout_seconds: int
    retry_count: int

    # 同步设置
    sync_wait_timeout_seconds: int

    # 状态
    status: str
    last_run_status: str | None
    last_result_message: str | None
    last_checked_at: datetime | None
    last_sync_at: datetime | None
    sync_deadline_at: datetime | None

    updated_at: datetime | None

    # 检测执行详情（仅 execute_check 返回）
    check_detail: str | None = None


class CookieSyncTaskCreateRequest(BaseModel):
    cookie_sync_task_name: str
    cookie_table: str = "ods_cookie_playwright"
    channel: str
    shop_name: str | None = None
    mobile_phone: str | None = None
    dns: str | None = None
    check_url: str
    http_method: str = "GET"
    http_headers: str | None = None
    http_body: str | None = None
    success_rule: str | None = None
    failure_rule: str | None = None
    cron_expression: str | None = None
    check_timeout_seconds: int = 30
    retry_count: int = 0
    sync_wait_timeout_seconds: int = 180


class CookieSyncTaskUpdateRequest(BaseModel):
    cookie_sync_task_name: str | None = None
    cookie_table: str | None = None
    channel: str | None = None
    shop_name: str | None = None
    mobile_phone: str | None = None
    dns: str | None = None
    check_url: str | None = None
    http_method: str | None = None
    http_headers: str | None = None
    http_body: str | None = None
    success_rule: str | None = None
    failure_rule: str | None = None
    cron_expression: str | None = None
    check_timeout_seconds: int | None = None
    retry_count: int | None = None
    sync_wait_timeout_seconds: int | None = None


class CookieSyncTaskToggleRequest(BaseModel):
    enabled: bool


class CookieSyncTaskListResponse(BaseModel):
    items: list[CookieSyncTaskResponse]
