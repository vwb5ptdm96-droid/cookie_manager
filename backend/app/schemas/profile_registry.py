from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProfileUpsertRequest(BaseModel):
    profile_key: str = Field(min_length=1, max_length=64)
    relative_path: str = Field(min_length=1, max_length=255)
    debug_port: int | None = Field(default=None, ge=1, le=65535)
    note: str | None = Field(default=None, max_length=500)


class ProfileLockRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=128)


class ProfileResponse(BaseModel):
    id: int
    profile_key: str
    relative_path: str
    absolute_path: str
    status: str
    is_locked: bool
    lock_owner: str | None
    debug_port: int | None
    note: str | None
    last_verified_at: datetime | None
    updated_at: datetime | None


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]
