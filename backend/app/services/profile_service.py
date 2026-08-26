from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.path_utils import PathSecurityError, resolve_runtime_path
from app.models.profile_registry import ProfileRegistry
from app.services.chrome_utils import (
    DEFAULT_DEBUG_PORT,
    find_chrome_executable,
    kill_chrome_for_profile,
    kill_chrome_on_port,
    launch_chrome_debug,
    wait_for_cdp,
)


@dataclass(frozen=True)
class ProfilePayload:
    profile_key: str
    relative_path: str
    debug_port: int | None = None
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
            row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.profile_key == payload.profile_key)
            ).scalar_one_or_none()

            if row is None:
                row = ProfileRegistry(
                    profile_key=payload.profile_key,
                    relative_path=relative_path,
                    debug_port=payload.debug_port,
                    note=payload.note,
                    status=status,
                    last_verified_at=datetime.now() if absolute_path.exists() else None,
                )
                session.add(row)
            else:
                row.relative_path = relative_path
                row.debug_port = payload.debug_port
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
        """更新 profile_key、路径等字段。"""
        relative_path = self._normalize_profile_relative_path(payload.relative_path)
        absolute_path = self._resolve_profile_path(relative_path)

        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)

            # 如果 profile_key 变了，检查新 key 是否已存在
            if payload.profile_key != profile_key:
                existing = session.execute(
                    select(ProfileRegistry).where(ProfileRegistry.profile_key == payload.profile_key)
                ).scalar_one_or_none()
                if existing:
                    raise AppError(f"Profile Key「{payload.profile_key}」已被使用", "DUPLICATE_PROFILE_KEY")

            row.profile_key = payload.profile_key
            row.relative_path = relative_path
            row.debug_port = payload.debug_port
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

    def open_debug(self, profile_key: str) -> dict[str, object]:
        """拉起带该目录（--user-data-dir）的可见 Chrome，并以 CDP 端口暴露供外部脚本连接调试。"""
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            if row.is_locked:
                raise AppError("目录已被脚本运行锁定，请先关闭运行或解锁", "DIRECTORY_LOCKED", status_code=409)
            port = row.debug_port or DEFAULT_DEBUG_PORT
            absolute_path = self._resolve_profile_path(row.relative_path)

        if not (1 <= port <= 65535):
            raise AppError("调试端口必须在 1-65535 之间", "INVALID_DEBUG_PORT")

        chrome_path = find_chrome_executable()
        if chrome_path is None:
            raise AppError("未找到 Chrome，请在 .env 配置 CHROME_PATH", "CHROME_NOT_FOUND", status_code=500)

        cdp_url = f"http://127.0.0.1:{port}"
        if wait_for_cdp(port, timeout=1.5):
            return {
                "profile_key": profile_key,
                "port": port,
                "cdp_url": cdp_url,
                "chrome_path": str(chrome_path),
                "already_running": True,
            }

        # 清理同目录/同端口的残留 Chrome，避免连接旧实例或锁文件残留
        kill_chrome_for_profile(absolute_path)
        kill_chrome_on_port(port)
        launch_chrome_debug(absolute_path, port, chrome_path)

        if not wait_for_cdp(port, timeout=15.0):
            # 清理已拉起的 Chrome，避免留下孤儿进程与目录锁文件
            kill_chrome_for_profile(absolute_path)
            kill_chrome_on_port(port)
            raise AppError(
                f"Chrome 已拉起但 CDP 端口 {port} 未就绪，已自动清理，请确认 Chrome 能正常打开或 CHROME_PATH 是否正确",
                "CDP_NOT_READY",
            )
        return {
            "profile_key": profile_key,
            "port": port,
            "cdp_url": cdp_url,
            "chrome_path": str(chrome_path),
            "already_running": False,
        }

    def close_debug(self, profile_key: str) -> dict[str, object]:
        """关闭该目录对应的调试 Chrome。

        按 user-data-dir 精确清理，不按端口杀：避免跨目录共用同一端口时误杀其他目录的调试窗口，
        也避免脚本运行中（锁定）时被误杀。
        """
        with Session(self.engine) as session:
            row = self._get_by_key(session, profile_key)
            if row.is_locked:
                raise AppError(
                    "目录已被脚本运行锁定，禁止关闭调试（避免误杀运行中脚本的 Chrome）",
                    "DIRECTORY_LOCKED",
                    status_code=409,
                )
            port = row.debug_port or DEFAULT_DEBUG_PORT
            absolute_path = self._resolve_profile_path(row.relative_path)
        kill_chrome_for_profile(absolute_path)
        return {"profile_key": profile_key, "port": port, "closed": True}

    def _get_by_key(self, session: Session, profile_key: str) -> ProfileRegistry:
        row = session.execute(
            select(ProfileRegistry).where(ProfileRegistry.profile_key == profile_key)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("Profile 不存在", "PROFILE_NOT_FOUND", status_code=404)
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
            "relative_path": row.relative_path,
            "absolute_path": str(self._resolve_profile_path(row.relative_path)),
            "status": row.status,
            "is_locked": row.is_locked,
            "lock_owner": row.lock_owner,
            "debug_port": row.debug_port,
            "note": row.note,
            "last_verified_at": row.last_verified_at,
            "updated_at": row.updated_at,
        }
