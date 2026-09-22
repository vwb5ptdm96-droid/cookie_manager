"""SRE 值班动作：无闸自检/解释；回收与重启必须 confirmed。"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Engine

from app.core.errors import AppError

logger = logging.getLogger(__name__)
BEIJING = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(BEIJING).replace(tzinfo=None)


def _append_audit(runtime_root: Path, action: str, payload: dict[str, Any]) -> None:
    path = Path(runtime_root) / "logs" / "sre-actions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now().isoformat(timespec="seconds"), "action": action, **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def require_confirm(confirmed: bool) -> None:
    if not confirmed:
        raise AppError("此操作必须在工作台确认后执行", "SRE_GATE_REQUIRED", status_code=400)


class SreService:
    def __init__(self, engine: Engine, runtime_root: Path, project_root: Path, app_port: int = 8081) -> None:
        self.engine = engine
        self.runtime_root = Path(runtime_root)
        self.project_root = Path(project_root)
        self.app_port = app_port

    def explain_backend(self) -> dict[str, Any]:
        from app.services.environment_service import EnvironmentService
        from app.services.log_query_service import LogQueryService

        health = self.probe_health()
        env = EnvironmentService(engine=self.engine, runtime_root=self.runtime_root).get_latest_checks()
        logs = LogQueryService(engine=self.engine).list_logs()
        items = logs.get("items") if isinstance(logs, dict) else []
        slim = []
        if isinstance(items, list):
            for row in items[:5]:
                if isinstance(row, dict):
                    slim.append(
                        {
                            "title": row.get("title"),
                            "status": row.get("status"),
                            "message": str(row.get("message") or "")[:240],
                        }
                    )
        return {"ok": True, "health": health, "env": env, "recent_logs": slim}

    def run_env_check(self) -> dict[str, Any]:
        from app.services.environment_service import EnvironmentService

        result = EnvironmentService(engine=self.engine, runtime_root=self.runtime_root).execute_checks()
        _append_audit(self.runtime_root, "env_check", {"ok": True})
        return {"ok": True, "result": result}

    def recycle_stale_runs(self, *, confirmed: bool) -> dict[str, Any]:
        require_confirm(confirmed)
        from app.services.health_task_service import HealthTaskService

        count = HealthTaskService(engine=self.engine, runtime_root=self.runtime_root).reap_stale_runs()
        _append_audit(self.runtime_root, "recycle_stale_runs", {"confirmed": True, "reclaimed": count})
        return {"ok": True, "reclaimed": count}

    def restart_backend(self, *, confirmed: bool, dry_run: bool | None = None) -> dict[str, Any]:
        require_confirm(confirmed)
        dry = dry_run if dry_run is not None else self._default_dry_run()
        bat = self.project_root / "restart_backend.bat"
        _append_audit(
            self.runtime_root,
            "restart_backend",
            {"confirmed": True, "dry_run": dry, "script": str(bat)},
        )
        if dry:
            return {
                "ok": True,
                "scheduled": False,
                "dry_run": True,
                "health": self.probe_health(),
                "message": "非 Windows 或 SRE_RESTART_DRY_RUN：未真正杀进程，已探活当前 /api/health",
            }
        if not bat.is_file():
            raise AppError("找不到 restart_backend.bat", "SRE_RESTART_SCRIPT_MISSING", status_code=500)
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            cwd=str(self.project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "ok": True,
            "scheduled": True,
            "dry_run": False,
            "message": "已调度重启，请等待工作台探活 /api/health",
        }

    def probe_health(self) -> dict[str, Any]:
        url = f"http://127.0.0.1:{self.app_port}/api/health"
        try:
            with httpx.Client(trust_env=False, timeout=3.0) as client:
                resp = client.get(url)
            return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "url": url}

    @staticmethod
    def _default_dry_run() -> bool:
        flag = (os.environ.get("SRE_RESTART_DRY_RUN") or "").strip().lower()
        if flag in {"1", "true", "yes"}:
            return True
        if flag in {"0", "false", "no"}:
            return False
        return os.name != "nt"
