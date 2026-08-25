from __future__ import annotations

import getpass
import importlib.util
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from app.models.env_check import EnvCheckResult


class EnvironmentService:
    def __init__(self, *, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root

    def execute_checks(self) -> dict[str, object]:
        items = [
            self._check_python_venv(),
            self._check_playwright(),
            self._check_chromium(),
            self._check_runtime_root(),
            self._check_runtime_subdir("profiles_dir", self.runtime_root / "profiles", "Profile 目录"),
            self._check_runtime_subdir("scripts_dir", self.runtime_root / "scripts", "脚本目录"),
            self._check_runtime_subdir("logs_dir", self.runtime_root / "logs", "日志目录"),
            self._check_database_connection(),
            self._check_legacy_table(),
            self._check_platform_network(),
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

    def _check_python_venv(self) -> dict[str, object]:
        in_venv = sys.prefix != sys.base_prefix
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        status = "PASS" if in_venv else "WARN"
        return {
            "check_code": "python_venv",
            "status": status,
            "summary": f"Python {py_version} @ {sys.executable}" + ("" if in_venv else "（未使用虚拟环境）"),
        }

    def _check_playwright(self) -> dict[str, object]:
        if importlib.util.find_spec("playwright") is None:
            return {
                "check_code": "playwright",
                "status": "FAIL",
                "summary": "Playwright 未安装，请执行 `playwright install chromium`",
            }
        return {
            "check_code": "playwright",
            "status": "PASS",
            "summary": "Playwright 已安装",
        }

    def _check_chromium(self) -> dict[str, object]:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
        except Exception as exc:
            return {
                "check_code": "chromium",
                "status": "FAIL",
                "summary": f"Chromium/Chrome 启动失败: {exc}",
            }
        return {
            "check_code": "chromium",
            "status": "PASS",
            "summary": "Chromium/Chrome 可正常启动",
        }

    def _check_legacy_table(self) -> dict[str, object]:
        try:
            inspector = inspect(self.engine)
            tables = set(inspector.get_table_names())
            legacy_tables = [t for t in tables if "cookie" in t.lower()]
            if legacy_tables:
                return {
                    "check_code": "legacy_table",
                    "status": "PASS",
                    "summary": f"检测到旧 cookie 表: {', '.join(sorted(legacy_tables))}",
                }
            return {
                "check_code": "legacy_table",
                "status": "WARN",
                "summary": "未找到含 cookie 的旧表，健康检测将无法查询登录态数据",
            }
        except Exception as exc:
            return {
                "check_code": "legacy_table",
                "status": "FAIL",
                "summary": f"旧 cookie 表查询失败: {exc}",
            }

    def _check_platform_network(self) -> dict[str, object]:
        probe_url = os.environ.get("NETWORK_PROBE_URL", "https://www.baidu.com")
        try:
            resp = httpx.get(probe_url, timeout=5)
            if resp.status_code < 400:
                return {
                    "check_code": "platform_network",
                    "status": "PASS",
                    "summary": f"网络可达: {probe_url} (HTTP {resp.status_code})",
                }
            return {
                "check_code": "platform_network",
                "status": "FAIL",
                "summary": f"网络探测返回异常状态: HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "check_code": "platform_network",
                "status": "FAIL",
                "summary": f"网络不可达: {probe_url} ({exc})",
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
            "summary": "未检测到明确桌面会话，headed 模式脚本可能需要桌面环境",
        }
