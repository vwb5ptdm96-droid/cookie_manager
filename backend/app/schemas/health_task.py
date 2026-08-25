from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthTaskResponse(BaseModel):
    id: int
    health_task_code: str
    health_task_name: str
    enabled: bool

    # 检测配置
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

    # 高级调度
    cron_expression: str | None
    check_timeout_seconds: int
    retry_count: int
    last_checked_at: datetime | None
    next_run_at: datetime | None

    # 失败修复
    auto_repair_enabled: bool
    repair_cron_expression: str | None
    repair_script_id: int | None
    repair_directory_id: int | None
    repair_run_mode: str | None
    repair_script_config: str | None
    repair_timeout_seconds: int

    # 状态
    status: str
    last_run_status: str | None
    last_result_message: str | None
    last_repaired_at: datetime | None
    last_repair_run_id: str | None

    updated_at: datetime | None

    # 检测执行详情（仅 execute_check 返回）
    check_detail: str | None = None


class HealthTaskCreateRequest(BaseModel):
    health_task_name: str
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
    auto_repair_enabled: bool = False
    repair_cron_expression: str | None = None
    repair_script_id: int | None = None
    repair_directory_id: int | None = None
    repair_run_mode: str | None = None
    repair_script_config: str | None = None
    repair_timeout_seconds: int = 600


class HealthTaskUpdateRequest(BaseModel):
    health_task_name: str | None = None
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
    auto_repair_enabled: bool | None = None
    repair_cron_expression: str | None = None
    repair_script_id: int | None = None
    repair_directory_id: int | None = None
    repair_run_mode: str | None = None
    repair_script_config: str | None = None
    repair_timeout_seconds: int | None = None


class HealthTaskToggleRequest(BaseModel):
    enabled: bool


class HealthTaskListResponse(BaseModel):
    items: list[HealthTaskResponse]
