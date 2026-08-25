from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.path_utils import PathSecurityError, resolve_runtime_path
from app.models.profile_registry import ProfileRegistry
from app.models.session_task import SessionMaintenanceTask


@dataclass(frozen=True)
class ProfilePayload:
    profile_key: str
    task_id: int | None
    relative_path: str
    note: str | None = None


class ProfileService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root

    def list_profiles(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(select(ProfileRegistry).order_by(ProfileRegistry.profile_key.asc())).scalars().all()
        return [self._serialize(row) for row in rows]

    def upsert(self, payload: ProfilePayload) -> dict[str, object]:
        relative_path = self._normalize_profile_relative_path(payload.relative_path)
        absolute_path = self._resolve_profile_path(relative_path)
        absolute_path.mkdir(parents=True, exist_ok=True)
        status = "READY"

        with Session(self.engine) as session:
            if payload.task_id is not None:
                self._get_task_by_id(session, payload.task_id)
            row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.profile_key == payload.profile_key)
            ).scalar_one_or_none()

            if row is None:
                row = ProfileRegistry(
                    profile_key=payload.profile_key,
                    task_id=payload.task_id,
                    relative_path=relative_path,
                    note=payload.note,
                    status=status,
                    last_verified_at=datetime.now() if absolute_path.exists() else None,
                )
                session.add(row)
            else:
                row.task_id = payload.task_id
                row.relative_path = relative_path
                row.note = payload.note
                row.status = status
                row.last_verified_at = datetime.now() if absolute_path.exists() else row.last_verified_at

            session.commit()
            session.refresh(row)

        return self._serialize(row)

    def lock(self, profile_key: str, owner: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            if row.is_locked and row.lock_owner != owner:
                raise AppError("Profile 已被其他任务锁定", "PROFILE_LOCKED", status_code=409)

            row.is_locked = True
            row.lock_owner = owner
            row.status = "LOCKED"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def unlock(self, profile_key: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            row.is_locked = False
            row.lock_owner = None
            if row.status == "LOCKED":
                row.status = "READY" if self._resolve_profile_path(row.relative_path).exists() else "MISSING"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def verify(self, profile_key: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            absolute_path = self._resolve_profile_path(row.relative_path)
            row.is_locked = False
            row.lock_owner = None
            row.last_verified_at = datetime.now()
            row.status = "READY" if absolute_path.exists() else "CORRUPTED"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def mark_risk(self, profile_key: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            row.status = "RISK"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def update(self, profile_key: str, payload: ProfilePayload) -> dict[str, object]:
        """更新 profile_key、路径、绑定任务等字段。"""
        relative_path = self._normalize_profile_relative_path(payload.relative_path)
        absolute_path = self._resolve_profile_path(relative_path)

        with Session(self.engine) as session:
            if payload.task_id is not None:
                self._get_task_by_id(session, payload.task_id)
            row = self._get_by_key(session, profile_key)

            # 如果 profile_key 变了，检查新 key 是否已存在
            if payload.profile_key != profile_key:
                existing = session.execute(
                    select(ProfileRegistry).where(ProfileRegistry.profile_key == payload.profile_key)
                ).scalar_one_or_none()
                if existing:
                    raise AppError(f"Profile Key「{payload.profile_key}」已被使用", "DUPLICATE_PROFILE_KEY")

            row.profile_key = payload.profile_key
            row.task_id = payload.task_id
            row.relative_path = relative_path
            row.note = payload.note
            row.last_verified_at = datetime.now() if absolute_path.exists() else row.last_verified_at

            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def delete(self, profile_key: str) -> None:
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            if row.is_locked:
                raise AppError("Profile 已被锁定，无法删除", "PROFILE_LOCKED", status_code=409)
            session.delete(row)
            session.commit()

    def _get_by_key(self, session: Session, profile_key: str) -> ProfileRegistry:
        row = session.execute(
            select(ProfileRegistry).where(ProfileRegistry.profile_key == profile_key)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("Profile 不存在", "PROFILE_NOT_FOUND", status_code=404)
        return row

    def _get_task_by_id(self, session: Session, task_id: int) -> SessionMaintenanceTask:
        row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.id == task_id)).scalar_one_or_none()
        if row is None:
            raise AppError("绑定任务不存在", "TASK_NOT_FOUND", status_code=404)
        return row

    def _normalize_profile_relative_path(self, relative_path: str) -> str:
        normalized = relative_path.strip().replace("\\", "/")

        # 禁止绝对路径
        if PureWindowsPath(normalized).is_absolute():
            raise AppError("禁止使用绝对路径，Profile 路径必须位于 runtime/profiles/ 内", "INVALID_PROFILE_PATH")

        # 必须位于 runtime/profiles 内
        if not normalized.startswith("profiles/"):
            raise AppError("Profile 路径必须位于 runtime/profiles/ 目录内", "INVALID_PROFILE_PATH")
        try:
            resolve_runtime_path(self.runtime_root, normalized)
        except PathSecurityError as exc:
            raise AppError(str(exc), "INVALID_PROFILE_PATH") from exc
        return normalized

    def _resolve_profile_path(self, relative_path: str) -> Path:
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return resolve_runtime_path(self.runtime_root, relative_path)

    def _serialize(self, row: ProfileRegistry) -> dict[str, object]:
        return {
            "id": row.id,
            "profile_key": row.profile_key,
            "task_id": row.task_id,
            "relative_path": row.relative_path,
            "absolute_path": str(self._resolve_profile_path(row.relative_path)),
            "status": row.status,
            "is_locked": row.is_locked,
            "lock_owner": row.lock_owner,
            "note": row.note,
            "last_verified_at": row.last_verified_at,
            "updated_at": row.updated_at,
        }
