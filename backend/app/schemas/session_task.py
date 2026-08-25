from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionTaskUpsertRequest(BaseModel):
    task_name: str = Field(min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=32)
    mobile_phone: str = Field(min_length=1, max_length=32)
    account_alias: str | None = Field(default=None, max_length=128)
    related_dns: list[str] = Field(min_length=1)
    script_code: str = Field(min_length=1, max_length=64)
    profile_key: str = Field(min_length=1, max_length=64)
    schedule_type: str = Field(default="MANUAL", min_length=1, max_length=32)
    schedule_value: str | None = Field(default=None, max_length=128)
    script_config: dict[str, object] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=500)


class SessionTaskToggleRequest(BaseModel):
    enabled: bool


class SessionTaskResponse(BaseModel):
    id: int
    task_code: str
    task_name: str
    channel: str
    mobile_phone: str
    account_alias: str | None
    related_dns: list[str]
    script_code: str
    script_name: str | None
    script_type: str | None
    platform: str | None
    profile_key: str
    profile_relative_path: str | None
    profile_absolute_path: str | None
    schedule_type: str
    schedule_value: str | None
    script_config: dict[str, object]
    script_dir: str | None
    script_main_file: str | None
    health_check_codes: list[str]
    status: str
    enabled: bool
    last_run_status: str | None
    last_run_id: str | None
    last_error: str | None
    last_artifact_dir: str | None
    last_run_at: datetime | None
    updated_at: datetime | None
    artifact_dir: str | None = None


class SessionTaskListResponse(BaseModel):
    items: list[SessionTaskResponse]
