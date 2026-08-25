from __future__ import annotations

import getpass
import os
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models.env_check import EnvCheckResult


class EnvironmentService:
    def __init__(self, *, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root

    def execute_checks(self) -> dict[str, object]:
        items = [
            self._check_runtime_root(),
            self._check_runtime_subdir("profiles_dir", self.runtime_root / "profiles", "Profile 目录"),
            self._check_runtime_subdir("scripts_dir", self.runtime_root / "scripts", "脚本目录"),
            self._check_runtime_subdir("logs_dir", self.runtime_root / "logs", "日志目录"),
            self._check_database_connection(),
            self._check_current_user(),
            self._check_desktop_session(),
        ]

        with Session(self.engine) as session:
            for item in items:
                session.add(
                    EnvCheckResult(
                        check_code=str(item["check_code"]),
                        status=str(item["status"]),
                        summary=str(item["summary"]),
                    )
                )
            session.commit()

        return {"items": items}

    def get_latest_checks(self) -> dict[str, object]:
        with Session(self.engine) as session:
            rows = session.execute(select(EnvCheckResult).order_by(EnvCheckResult.created_at.desc(), EnvCheckResult.id.desc())).scalars().all()

        latest_by_code: dict[str, dict[str, object]] = {}
        for row in rows:
            if row.check_code in latest_by_code:
                continue
            latest_by_code[row.check_code] = {
                "check_code": row.check_code,
                "status": row.status,
                "summary": row.summary,
                "created_at": row.created_at,
            }

        return {"items": list(latest_by_code.values())}

    def _check_runtime_root(self) -> dict[str, object]:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        return {
            "check_code": "runtime_root",
            "status": "PASS",
            "summary": f"运行目录可访问: {self.runtime_root}",
        }

    def _check_runtime_subdir(self, check_code: str, path: Path, label: str) -> dict[str, object]:
        path.mkdir(parents=True, exist_ok=True)
        return {
            "check_code": check_code,
            "status": "PASS",
            "summary": f"{label}可访问: {path}",
        }

    def _check_database_connection(self) -> dict[str, object]:
        try:
            with Session(self.engine) as session:
                session.execute(select(1)).scalar_one()
        except Exception as exc:
            return {
                "check_code": "database_connection",
                "status": "FAIL",
                "summary": f"数据库连接失败: {exc}",
            }
        return {
            "check_code": "database_connection",
            "status": "PASS",
            "summary": "数据库连接正常",
        }

    def _check_current_user(self) -> dict[str, object]:
        return {
            "check_code": "current_user",
            "status": "PASS",
            "summary": f"当前运行用户: {getpass.getuser()}",
        }

    def _check_desktop_session(self) -> dict[str, object]:
        session_name = os.environ.get("SESSIONNAME", "").strip()
        if session_name:
            return {
                "check_code": "desktop_session",
                "status": "PASS",
                "summary": f"检测到桌面会话: {session_name}",
            }
        return {
            "check_code": "desktop_session",
            "status": "WARN",
            "summary": "未检测到明确桌面会话，人工修复前请确认通过 RDP 登录部署机",
        }
