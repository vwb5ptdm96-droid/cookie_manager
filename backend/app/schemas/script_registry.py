from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScriptResponse(BaseModel):
    id: int
    script_code: str
    script_name: str
    script_type: str
    platform: str
    version: str | None
    profile_key: str | None
    script_dir: str
    absolute_dir: str
    main_file: str
    enabled: bool
    default_run_mode: str | None
    default_cdp_port: int | None = None
    supports_pause: bool
    supports_cancel: bool
    default_timeout_seconds: int
    description: str | None
    updated_at: datetime | None


class ScriptToggleRequest(BaseModel):
    enabled: bool


class ScriptProfileRequest(BaseModel):
    profile_key: str | None = None


class ScriptRunConfigRequest(BaseModel):
    default_run_mode: str | None = None
    default_cdp_port: int | None = None
    supports_pause: bool | None = None
    supports_cancel: bool | None = None
    default_timeout_seconds: int | None = None


class ScriptMainFileRequest(BaseModel):
    main_file: str = Field(min_length=1, max_length=255)


class ScriptUpdateRequest(BaseModel):
    script_name: str | None = None
    script_type: str | None = None
    platform: str | None = None
    description: str | None = None


class ScriptListResponse(BaseModel):
    items: list[ScriptResponse]
