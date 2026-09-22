"""站点值班 / 排障工具箱。能力靠工具集约束，不靠嘱咐。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from app.core.config import get_settings
from app.services.ops_summary_service import build_ops_summary

WATCHER_TOOLS = (
    "site_ops_summary",
    "site_list_health_tasks",
    "site_list_cookie_sync",
    "site_list_script_runs",
    "site_list_tickets",
    "site_get_logs",
    "site_env_last_check",
    "site_deploy_info",
    "ticket_pack_get",
)

REPAIRER_EXTRA = (
    "cdp_inspect",
    "cdp_click_safe",
    "script_read",
    "script_edit",
    "health_recheck",
    "ticket_conclude",
)

COLLECTOR_TOOLS = (
    "ticket_pack_get",
    "sync_mapping_get",
    "sync_dispatch",
    "sync_recheck",
    "ticket_conclude",
)


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


def tool_specs(role: str) -> list[dict[str, Any]]:
    watcher = [
        _schema("site_ops_summary", "今日值班计数早报（只读）", {}),
        _schema("site_list_health_tasks", "列出健康检测任务", {"status": {"type": "string"}}),
        _schema("site_list_cookie_sync", "列出采集任务", {"status": {"type": "string"}}),
        _schema("site_list_script_runs", "列出脚本运行", {"status": {"type": "string"}}),
        _schema("site_list_tickets", "列出自动排障工单", {"status": {"type": "string"}}),
        _schema("site_get_logs", "检索运行日志（脱敏截断）", {"keyword": {"type": "string"}}),
        _schema("site_env_last_check", "最近一次环境自检", {}),
        _schema("site_deploy_info", "部署路径与端口（无密钥）", {}),
        _schema("ticket_pack_get", "读取当前绑定工单实例包", {}),
    ]
    repairer = [
        _schema("cdp_inspect", "探查本单 CDP 页面并截图", {}),
        _schema("cdp_click_safe", "点击可逆关闭弹窗", {"selector": {"type": "string"}}, ["selector"]),
        _schema("script_read", "读取本单维护脚本", {}),
        _schema("script_edit", "改写本单维护脚本（先备份）", {"content": {"type": "string"}}, ["content"]),
        _schema("health_recheck", "对绑定健康检测任务复检（follow_up=false）", {}),
        _schema(
            "ticket_conclude",
            "结构化关单。SOLVED 必须先 health_recheck=PASS",
            {
                "status": {"type": "string", "enum": ["SOLVED", "NEED_HUMAN", "FAILED"]},
                "reason": {"type": "string"},
            },
            ["status"],
        ),
    ]
    if role == "repairer":
        return watcher + repairer
    if role == "collector":
        return [
            _schema("ticket_pack_get", "读取本采集工单实例包", {}),
            _schema("sync_mapping_get", "只读查询本任务采集映射", {}),
            _schema("sync_dispatch", "重派扩展补采（现有采集修复）", {}),
            _schema("sync_recheck", "采集任务复检（follow_up=false）", {}),
            _schema(
                "ticket_conclude",
                "结构化关单。采集 SOLVED 必须先 sync_recheck=PASS；无映射只能 NEED_HUMAN",
                {
                    "status": {"type": "string", "enum": ["SOLVED", "NEED_HUMAN", "FAILED"]},
                    "reason": {"type": "string"},
                },
                ["status"],
            ),
        ]
    return watcher


def validate_ticket_conclude(
    *,
    requested: str,
    issue_type: str | None,
    last_recheck: str | None,
    kind: str = "auto_repair",
) -> dict[str, Any]:
    status = (requested or "").strip().upper()
    issue = (issue_type or "FAIL").upper()
    kind = "cookie_sync" if kind == "cookie_sync" else "auto_repair"
    if status not in {"SOLVED", "NEED_HUMAN", "FAILED"}:
        return {"ok": False, "error": "status 必须是 SOLVED/NEED_HUMAN/FAILED"}
    if kind == "cookie_sync":
        if issue == "NO_MAPPING" and status == "SOLVED":
            return {"ok": False, "error": "无映射禁止 SOLVED，只能 NEED_HUMAN"}
        if status == "SOLVED" and last_recheck != "PASS":
            return {"ok": False, "error": "SOLVED 必须先 sync_recheck 且结果为 PASS", "recheck": last_recheck or "MISSING"}
        return {"ok": True, "status": status, "recheck": last_recheck or "SKIPPED", "stop_loop": True}
    if issue == "RISK" and status == "SOLVED":
        return {"ok": False, "error": "RISK 工单禁止 SOLVED"}
    if status == "SOLVED" and last_recheck != "PASS":
        return {"ok": False, "error": "SOLVED 必须先 health_recheck 且结果为 PASS", "recheck": last_recheck or "MISSING"}
    return {"ok": True, "status": status, "recheck": last_recheck or "SKIPPED", "stop_loop": True}


class ToolRuntime:
    def __init__(
        self,
        *,
        engine: Engine,
        runtime_root: Path,
        project_root: Path,
        role: str,
        ticket: dict[str, Any] | None = None,
        run_ctx: dict[str, Any] | None = None,
    ) -> None:
        self.engine = engine
        self.runtime_root = Path(runtime_root)
        self.project_root = Path(project_root)
        self.role = role
        self.ticket = ticket or {}
        self.run_ctx = run_ctx if run_ctx is not None else {}
        self.last_recheck: str | None = None
        self.allowed: set[str] = set(WATCHER_TOOLS)
        if role == "repairer":
            self.allowed.update(REPAIRER_EXTRA)
            if str(self.ticket.get("issue_type") or "").upper() == "RISK":
                self.allowed.discard("cdp_click_safe")
                self.allowed.discard("script_edit")
        elif role == "collector":
            self.allowed = set(COLLECTOR_TOOLS)

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.allowed:
            return {"ok": False, "error": f"当前角色 {self.role} 不能使用 {name}"}
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"未知工具 {name}"}
        return handler(args)

    def _trim(self, rows: list[dict[str, Any]], keys: tuple[str, ...], limit: int = 15) -> list[dict[str, Any]]:
        out = []
        for row in rows[:limit]:
            out.append({k: row.get(k) for k in keys if k in row})
        return out

    def _tool_site_ops_summary(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "data": build_ops_summary(self.engine)}

    def _tool_site_list_health_tasks(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.health_task_service import HealthTaskService

        rows = HealthTaskService(engine=self.engine, runtime_root=self.runtime_root).list_tasks()
        status = str(args.get("status") or "").strip()
        if status:
            rows = [r for r in rows if str(r.get("status") or r.get("last_run_status")) == status]
        return {
            "ok": True,
            "items": self._trim(
                rows,
                ("health_task_code", "health_task_name", "channel", "shop_name", "status", "last_run_status", "enabled"),
            ),
        }

    def _tool_site_list_cookie_sync(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.cookie_sync_task_service import CookieSyncTaskService

        rows = CookieSyncTaskService(engine=self.engine).list_tasks()
        status = str(args.get("status") or "").strip()
        if status:
            rows = [r for r in rows if str(r.get("status") or r.get("last_run_status")) == status]
        return {
            "ok": True,
            "items": self._trim(
                rows,
                ("cookie_sync_task_code", "cookie_sync_task_name", "channel", "shop_name", "status", "last_run_status"),
            ),
        }

    def _tool_site_list_script_runs(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.script_run_service import ScriptRunService

        status = str(args.get("status") or "").strip() or None
        rows = ScriptRunService(engine=self.engine, runtime_root=self.runtime_root).list_runs(status=status)
        items = [dict(row) for row in rows]
        return {
            "ok": True,
            "items": self._trim(items, ("run_id", "status", "health_task_code", "script_code", "directory_key")),
        }

    def _tool_site_list_tickets(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.auto_repair_ticket_service import AutoRepairTicketService

        status = str(args.get("status") or "").strip() or None
        rows = AutoRepairTicketService(engine=self.engine).list_tickets(status=status, limit=20)
        return {
            "ok": True,
            "items": self._trim(rows, ("id", "ticket_code", "shop_name", "channel", "status", "issue_type")),
        }

    def _tool_site_get_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.log_query_service import LogQueryService

        data = LogQueryService(engine=self.engine).list_logs(keyword=str(args.get("keyword") or "") or None)
        items = data.get("items") if isinstance(data, dict) else []
        rows = items if isinstance(items, list) else []
        slim = []
        for row in rows[:10]:
            if isinstance(row, dict):
                slim.append(
                    {
                        "title": row.get("title"),
                        "status": row.get("status"),
                        "message": str(row.get("message") or "")[:240],
                    }
                )
        return {"ok": True, "items": slim}

    def _tool_site_env_last_check(self, _args: dict[str, Any]) -> dict[str, Any]:
        from app.services.environment_service import EnvironmentService

        data = EnvironmentService(engine=self.engine, runtime_root=self.runtime_root).get_latest_checks()
        return {"ok": True, "data": data}

    def _tool_site_deploy_info(self, _args: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        return {
            "ok": True,
            "data": {
                "app_port": settings.app_port,
                "runtime_root": str(settings.runtime_root),
                "deploy_root": str(settings.deploy_root),
            },
        }

    def _tool_ticket_pack_get(self, _args: dict[str, Any]) -> dict[str, Any]:
        if not self.ticket:
            return {"ok": False, "error": "未绑定工单"}
        return {
            "ok": True,
            "ticket": {
                "ticket_code": self.ticket.get("ticket_code"),
                "status": self.ticket.get("status"),
                "issue_type": self.ticket.get("issue_type"),
                "kind": self.ticket.get("kind") or "auto_repair",
                "channel": self.ticket.get("channel"),
                "shop_name": self.ticket.get("shop_name"),
                "health_task_code": self.ticket.get("health_task_code"),
                "cookie_sync_task_code": self.ticket.get("cookie_sync_task_code"),
                "cdp_port": self.ticket.get("cdp_port"),
                "error_message": self.ticket.get("error_message"),
            },
            "run_ctx": {k: self.run_ctx.get(k) for k in ("script_path", "health_task_code", "cookie_sync_task_code", "profile_key") if k in self.run_ctx},
        }

    def _cdp_cmd(self, action: str, extra: list[str]) -> dict[str, Any]:
        port = int(self.ticket.get("cdp_port") or 0)
        if not port:
            return {"ok": False, "error": "无 cdp_port"}
        inspector = self.project_root / "tools" / "cdp_inspector.py"
        cmd = [sys.executable, str(inspector), "--port", str(port), "--action", action, *extra]
        completed = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        text = (completed.stdout or "")[-1500:]
        return {"ok": completed.returncode == 0, "output": text, "returncode": completed.returncode}

    def _tool_cdp_inspect(self, _args: dict[str, Any]) -> dict[str, Any]:
        code = str(self.ticket.get("ticket_code") or "unknown")
        shot = self.runtime_root / "artifacts" / code / "shot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        return self._cdp_cmd("inspect", ["--screenshot", str(shot)])

    def _tool_cdp_click_safe(self, args: dict[str, Any]) -> dict[str, Any]:
        selector = str(args.get("selector") or "").strip()
        if not selector:
            return {"ok": False, "error": "缺少 selector"}
        return self._cdp_cmd("click", ["--selector", selector])

    def _script_path(self) -> Path | None:
        from app.services.agent_repair_dispatcher import AgentRepairDispatcher

        d = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
        d.project_root = self.project_root
        return d._governed_script_path(str(self.run_ctx.get("script_path") or self.ticket.get("script_code") or "") or None)

    def _tool_script_read(self, _args: dict[str, Any]) -> dict[str, Any]:
        path = self._script_path()
        if path is None or not path.is_file():
            return {"ok": False, "error": "本单脚本不存在或不在 runtime/scripts"}
        return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")[:12000]}

    def _tool_script_edit(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._script_path()
        if path is None or not path.is_file():
            return {"ok": False, "error": "本单脚本不存在或不在 runtime/scripts"}
        content = str(args.get("content") or "")
        if not content.strip():
            return {"ok": False, "error": "content 为空"}
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": len(content.encode("utf-8"))}

    def _tool_health_recheck(self, _args: dict[str, Any]) -> dict[str, Any]:
        from app.services.health_task_service import HealthTaskService

        code = str(self.ticket.get("health_task_code") or "").strip()
        if not code:
            self.last_recheck = "SKIPPED"
            return {"ok": False, "error": "无 health_task_code", "recheck": "SKIPPED"}
        result = HealthTaskService(engine=self.engine, runtime_root=self.runtime_root).execute_check(
            code, follow_up=False
        )
        status = str(result.get("status") or "").upper()
        self.last_recheck = "PASS" if status == "PASS" else "FAIL"
        return {"ok": True, "recheck": self.last_recheck, "health_task_code": code, "run": result.get("status")}

    def _tool_ticket_conclude(self, args: dict[str, Any]) -> dict[str, Any]:
        verdict = validate_ticket_conclude(
            requested=str(args.get("status") or ""),
            issue_type=str(self.ticket.get("issue_type") or ""),
            last_recheck=self.last_recheck,
            kind="cookie_sync" if self.role == "collector" else str(self.ticket.get("kind") or "auto_repair"),
        )
        if verdict.get("ok"):
            verdict["reason"] = str(args.get("reason") or "")[:800]
        return verdict

    def _cookie_task_code(self) -> str:
        return str(
            self.ticket.get("cookie_sync_task_code")
            or self.run_ctx.get("cookie_sync_task_code")
            or self.ticket.get("health_task_code")
            or ""
        ).strip()

    def _tool_sync_mapping_get(self, _args: dict[str, Any]) -> dict[str, Any]:
        from app.services.cookie_sync_task_service import CookieSyncTaskService

        code = self._cookie_task_code()
        if not code:
            return {"ok": False, "error": "无 cookie_sync_task_code"}
        mapping = CookieSyncTaskService(engine=self.engine).lookup_mapping(code)
        if mapping is None:
            return {"ok": True, "mapped": False}
        return {"ok": True, "mapped": True, "mapping": mapping}

    def _tool_sync_dispatch(self, _args: dict[str, Any]) -> dict[str, Any]:
        from app.core.errors import AppError
        from app.services.cookie_sync_task_service import CookieSyncTaskService

        code = self._cookie_task_code()
        if not code:
            return {"ok": False, "error": "无 cookie_sync_task_code"}
        try:
            result = CookieSyncTaskService(engine=self.engine).execute_sync_repair(code)
        except AppError as exc:
            return {"ok": False, "error": exc.message, "error_code": exc.error_code}
        return {"ok": True, "status": result.get("status"), "detail": result.get("check_detail")}

    def _tool_sync_recheck(self, _args: dict[str, Any]) -> dict[str, Any]:
        from app.services.cookie_sync_task_service import CookieSyncTaskService

        code = self._cookie_task_code()
        if not code:
            self.last_recheck = "SKIPPED"
            return {"ok": False, "error": "无 cookie_sync_task_code", "recheck": "SKIPPED"}
        result = CookieSyncTaskService(engine=self.engine).execute_check(code, follow_up=False)
        status = str(result.get("status") or "").upper()
        self.last_recheck = "PASS" if status == "PASS" else "FAIL"
        return {"ok": True, "recheck": self.last_recheck, "cookie_sync_task_code": code, "status": result.get("status")}
