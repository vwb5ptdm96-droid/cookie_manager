from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RepairActionRequest(BaseModel):
    repaired_by: str | None = Field(default=None, max_length=128)


class RepairTicketResponse(BaseModel):
    ticket_code: str
    task_code: str
    task_name: str
    profile_key: str
    profile_path: str
    risk_type: str
    risk_message: str
    status: str
    repaired_by: str | None
    browser_artifact_dir: str | None
    browser_opened_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class RepairTicketListResponse(BaseModel):
    items: list[RepairTicketResponse]
