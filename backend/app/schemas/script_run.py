from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ScriptRunResponse(BaseModel):
    id: int
    run_id: str
    health_task_id: int | None
    health_task_code: str | None
    health_task_name: str | None = None
    script_id: int
    script_code: str
    script_name: str | None = None
    directory_id: int | None
    directory_key: str | None
    run_mode: str
    script_config: str | None
    timeout_seconds: int
    status: str
    pid: int | None
    start_time: datetime | None
    end_time: datetime | None
    duration_ms: int | None
    artifact_dir: str | None
    log_file: str | None
    result_json: str | None
    error_message: str | None
    exit_code: int | None
    control_file: str | None
    created_at: datetime | None
    updated_at: datetime | None


class ScriptRunListResponse(BaseModel):
    items: list[ScriptRunResponse]


class ScriptRunControlRequest(BaseModel):
    action: str  # "pause" / "resume" / "cancel"
