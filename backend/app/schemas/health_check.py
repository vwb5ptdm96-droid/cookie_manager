from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthCheckCreateRequest(BaseModel):
    check_name: str = Field(min_length=1, max_length=128)
    cookie_table: str = Field(default="ods_cookie_playwright", min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=32)
    shop_name: str = Field(min_length=1, max_length=128)
    mobile_phone: str = Field(min_length=1, max_length=32)
    dns: str = Field(min_length=1, max_length=128)
    method: str = Field(min_length=1, max_length=16)
    check_url: str = Field(min_length=1, max_length=500)
    request_headers: dict[str, object] = Field(default_factory=dict)
    request_body: dict[str, object] = Field(default_factory=dict)
    success_rule: dict[str, object] = Field(default_factory=dict)
    failure_rule: dict[str, object] = Field(default_factory=dict)
    trigger_task_id: int


class HealthCheckToggleRequest(BaseModel):
    enabled: bool


class HealthCheckResponse(BaseModel):
    id: int
    check_code: str
    check_name: str
    cookie_table: str
    channel: str
    shop_name: str
    mobile_phone: str
    dns: str
    method: str
    check_url: str
    request_headers: dict[str, object]
    request_body: dict[str, object]
    success_rule: dict[str, object]
    failure_rule: dict[str, object]
    trigger_task_id: int | None
    trigger_task_code: str | None
    status: str
    enabled: bool
    last_result_message: str | None
    last_checked_at: datetime | None
    updated_at: datetime | None
    triggered_task_code: str | None = None


class HealthCheckListResponse(BaseModel):
    items: list[HealthCheckResponse]
