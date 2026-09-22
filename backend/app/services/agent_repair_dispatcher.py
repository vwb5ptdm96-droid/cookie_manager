"""自动排障唤起与收尾编排（Spec REQ-011 / SCOPE-019）。

职责：
1. 建单/复用自动排障工单（独立 Session，经 AutoRepairTicketService）；
2. 落库冷却/预算校验通过后，以受限子进程唤起本机 claude CLI
   （cwd=项目根，使其加载 Auto-Repair Worker 语境与 .claude 工具链）；
3. 后台线程等待/超时强杀，解析 claude 输出的机器可读结果回写工单；
4. 终态决策：SOLVED 关闭；NEED_HUMAN/FAILED/超时 → 关闭 CDP 端口 + 飞书转人工。

不向调用方抛异常：任何失败都落工单终态并（尽力）飞书告警。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import difflib
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from app.services.auto_repair_ticket_service import AutoRepairTicketService
from app.services.chrome_utils import kill_chrome_on_port
from app.services.notification_service import send_feishu_notification

logger = logging.getLogger(__name__)

# Slice A：DeepSeek 直连 + 无人值守 CLI（见 docs/agent/ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md）
DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"
DEEPSEEK_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TURNS = 30
DEFAULT_MAX_SECONDS = 900
_PROXY_ENV_NAMES = frozenset({"http_proxy", "https_proxy", "all_proxy"})
_CLAUDE_BINARIES = ("claude.cmd", "claude")

# 机器可读结果：只认 TICKET_RESULT 前缀（避免正文/tool 的裸 "result:" 误判）。
# 允许行中、markdown 加粗/反引号包裹（生产会出现「**结论**：`TICKET_RESULT: NEED_HUMAN`」）；
# 仍要求完整前缀，多个命中取最后一个。
_RESULT_PATTERN = re.compile(
    r"(?i)(?<![\w])[`*]*TICKET_RESULT[` \t]*[:：][ \t`*]*?(SOLVED|NEED_HUMAN|FAILED)\b",
)
_RESULT_STATUSES = ("SOLVED", "NEED_HUMAN", "FAILED")
_CONCLUSION_MAX_CHARS = 4000


def _mask_line(line: str) -> str:
    """对日志行内的敏感内容（cookie/token/密码/手机号）脱敏后再落盘/记录。"""
    from app.services.health_task_service import HealthTaskService  # 延迟导入复用既有脱敏

    return HealthTaskService._mask_sensitive(line)


class AgentRepairDispatcher:
    """单次定向排障的唤起与收尾。全局限流并发上限，收尾在线程内完成不阻塞调用方。"""

    _max_concurrent = 2
    _slot = threading.BoundedSemaphore(_max_concurrent)

    def __init__(
        self,
        ticket_service: AutoRepairTicketService,
        project_root: Path,
        logs_root: Path,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_seconds: int = DEFAULT_MAX_SECONDS,
    ) -> None:
        self.ticket_service = ticket_service
        self.project_root = Path(project_root)
        self.logs_root = Path(logs_root)
        self.max_turns = max_turns
        self.max_seconds = max_seconds
        self._claude_path: str | None | bool = None  # None=未探测；False=缺失

    # ── 对外 ──

    def dispatch(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> dict[str, Any]:
        """唤起一次 claude 排障并后台收尾。

        ticket: service 序列化工单（含 id/ticket_code/cdp_port/channel/shop_name 等）
        run_ctx: {script_path?, health_task_name?, shop_name?} 唤起与通知用
        返回 {dispatched: bool, reason: str, ticket_id, ticket_code, pid?}
        """
        ticket_id = int(ticket["id"])
        ticket_code = ticket["ticket_code"]

        if not self._slot.acquire(blocking=False):
            return self._fail_now(ticket, run_ctx, "已达排障并发上限，稍后由冷却策略重试")

        # acquire 后所有提前 return 都必须 release；正常路径把许可转交收尾线程 release
        use_cli = self._use_cli_compat()
        proc: subprocess.Popen | None = None
        try:
            auth_token = self._resolve_auth_token(os.environ)
            if not auth_token:
                self._slot.release()
                return self._fail_now(
                    ticket,
                    run_ctx,
                    "未找到 DeepSeek API Key（DEEPSEEK_API_KEY / ANTHROPIC_AUTH_TOKEN / ~/.claude/settings.json）",
                )
            claude = None
            if use_cli:
                claude = self._resolve_claude()
                if claude is None:
                    self._slot.release()
                    return self._fail_now(ticket, run_ctx, "本机未找到 claude CLI（兼容层 AUTO_REPAIR_USE_CLI=1），无法唤起排障")
            is_collector = str(ticket.get("kind") or "") == "cookie_sync"
            if is_collector:
                use_cli = False
            if not is_collector:
                self._acquire_profile_lock(ticket, run_ctx)
                self._prepare_script_backup(ticket, run_ctx)
            prompt = self._build_prompt(ticket, run_ctx) if not is_collector else self._build_collector_prompt(ticket, run_ctx)
            log_file = self._prepare_log_file(ticket_code)
            workdir = Path(self.logs_root).parent / "artifacts" / ticket_code
            workdir.mkdir(parents=True, exist_ok=True)
            run_ctx["ticket_dir"] = str(workdir)
            (workdir / "ticket_pack.json").write_text(
                json.dumps({"ticket": ticket, "run_ctx": {k: run_ctx.get(k) for k in ("script_path", "health_task_code", "cookie_sync_task_code", "profile_key")}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            pid_path = workdir / "agent.pid"
            if use_cli:
                config_dir = self._ensure_isolated_config(self.logs_root.parent / "cache" / "claude_agent")
                child_env = self._build_child_env(os.environ, auth_token=auth_token, config_dir=config_dir)
                child_env["AUTO_REPAIR_TICKET_DIR"] = str(workdir)
                child_env["AUTO_REPAIR_PROJECT_ROOT"] = str(self.project_root)
                cmd = self._build_command(str(claude), prompt)
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(workdir),
                    stdout=open(log_file, "w", encoding="utf-8"),
                    stderr=subprocess.STDOUT,
                    env=child_env,
                )
                pid_path.write_text(str(proc.pid), encoding="utf-8")
            else:
                pid_path.write_text("loop", encoding="utf-8")
        except Exception as exc:
            try:
                self._release_profile_lock(run_ctx)
            except Exception:
                pass
            self._slot.release()
            logger.exception("[AutoRepair] 唤起排障失败 ticket=%s", ticket_code)
            return self._fail_now(ticket, run_ctx, f"唤起排障失败: {exc}")

        try:
            self.ticket_service.mark_dispatched(
                channel=ticket.get("channel") or "",
                shop_name=ticket.get("shop_name"),
                ticket_id=ticket_id,
            )
        except Exception:
            logger.exception("[AutoRepair] 标记 RUNNING 失败 ticket=%s", ticket_code)

        try:
            if use_cli and proc is not None:
                threading.Thread(
                    target=self._reap,
                    args=(proc, ticket, run_ctx, log_file),
                    name=f"auto-repair-{ticket_code}",
                    daemon=True,
                ).start()
                pid_out: int | str = proc.pid
            else:
                threading.Thread(
                    target=self._reap_loop,
                    args=(ticket, run_ctx, log_file, auth_token, prompt),
                    name=f"auto-repair-{ticket_code}",
                    daemon=True,
                ).start()
                pid_out = 0
        except Exception:
            if proc is not None:
                try:
                    self._kill_tree(proc.pid)
                except Exception:
                    pass
            self._slot.release()
            logger.exception("[AutoRepair] 收尾线程创建失败 ticket=%s", ticket_code)
            return self._fail_now(ticket, run_ctx, "收尾线程创建失败")

        logger.info("[AutoRepair] 已唤起排障 ticket=%s mode=%s", ticket_code, "cli" if use_cli else "loop")
        return {
            "dispatched": True,
            "reason": "ok",
            "ticket_id": ticket_id,
            "ticket_code": ticket_code,
            "pid": pid_out,
            "mode": "cli" if use_cli else "loop",
        }

    # ── 收尾 ──

    def _reap(
        self,
        proc: subprocess.Popen,
        ticket: dict[str, Any],
        run_ctx: dict[str, Any],
        log_file: Path,
    ) -> None:
        ticket_id = int(ticket["id"])
        ticket_code = ticket["ticket_code"]
        gov_status = "FAILED"
        try:
            status = self._wait_process(proc)  # 'ok' 或 'timeout'
            text = self._read_log(log_file)
            from app.services.agent_event_builder import unwrap_cli_log

            body, usage = unwrap_cli_log(text)
            if not usage:
                from app.services.agent_event_builder import collect_usage_from_claude_sessions

                usage = collect_usage_from_claude_sessions(
                    ticket_code,
                    [
                        Path(self.logs_root).parent / "cache" / "claude_agent",
                        Path.home() / ".claude",
                    ],
                )
            if usage:
                usage_path = Path(self.logs_root).parent / "artifacts" / ticket_code / "usage.json"
                usage_path.parent.mkdir(parents=True, exist_ok=True)
                usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
            result = self._parse_result(body or text)

            if status == "timeout" or result not in _RESULT_STATUSES or proc.returncode not in (0, None):
                # 超时 / 无结果 / 非零退出 → 视为排障失败
                tail = _mask_line(text[-1500:])
                self.ticket_service.record_result(
                    ticket_id,
                    status="FAILED",
                    diagnosis=tail or None,
                    error_message=f"排障{'超时强制终止' if status == 'timeout' else '无有效结果或异常退出'}",
                )
                self._shutdown_browser(ticket)
                self._notify_need_human(ticket, run_ctx, "自动排障失败（超时/无结果），需人工介入", tail[-800:])
                return

            final_status, extra = self._finalize_agent_result(ticket, result)
            gov_status = final_status
            diagnosis = _mask_line(text[-_CONCLUSION_MAX_CHARS:])
            if extra:
                diagnosis = ((diagnosis or "") + "\n" + extra).strip()
            if final_status == "SOLVED":
                self.ticket_service.record_result(
                    ticket_id, status="SOLVED", diagnosis=diagnosis or "claude 未输出诊断说明"
                )
                logger.info("[AutoRepair] 工单 %s 排障成功（健康复检 PASS）", ticket_code)
                return

            self.ticket_service.record_result(
                ticket_id,
                status=final_status,
                diagnosis=diagnosis or "claude 判定需人工介入",
            )
            self._notify_need_human(ticket, run_ctx, extra or "自动排障判定需人工介入（人机验证/无法确认）", (diagnosis or "")[-1200:])
        except Exception:
            logger.exception("[AutoRepair] 收尾处理异常 ticket=%s", ticket_code)
            try:
                self.ticket_service.record_result(ticket_id, status="FAILED", error_message="收尾处理异常")
            except Exception:
                pass
        finally:
            try:
                self._shutdown_browser(ticket)
            except Exception:
                logger.exception("[AutoRepair] 关闭 CDP 调试浏览器失败 ticket=%s", ticket_code)
            try:
                self._apply_script_governance(ticket, run_ctx, gov_status)
            except Exception:
                logger.exception("[AutoRepair] 脚本备份/回滚失败 ticket=%s", ticket_code)
            try:
                self._release_profile_lock(run_ctx)
            except Exception:
                logger.exception("[AutoRepair] 释放目录锁失败 ticket=%s", ticket_code)
            self._slot.release()

    def _reap_loop(
        self,
        ticket: dict[str, Any],
        run_ctx: dict[str, Any],
        log_file: Path,
        auth_token: str,
        prompt: str,
    ) -> None:
        ticket_id = int(ticket["id"])
        ticket_code = ticket["ticket_code"]
        gov_status = "FAILED"
        log_handle = log_file.open("a", encoding="utf-8")
        try:
            from app.services.agent_loop import deepseek_complete, run_tool_loop
            from app.services.agent_tools import ToolRuntime, tool_specs

            role = "collector" if str(ticket.get("kind") or "") == "cookie_sync" else "repairer"
            runtime = ToolRuntime(
                engine=self.ticket_service.engine,
                runtime_root=Path(self.logs_root).parent,
                project_root=self.project_root,
                role=role,
                ticket=ticket,
                run_ctx=run_ctx,
            )

            def on_event(kind: str, payload: dict[str, Any]) -> None:
                text = json.dumps(payload, ensure_ascii=False)[:2000]
                log_handle.write(f"[{kind}] {text}\n")
                log_handle.flush()

            system = (
                "你是采集 Collector。禁止 CDP 和改脚本。无映射只能 NEED_HUMAN。SOLVED 必须先 sync_recheck=PASS。"
                if role == "collector"
                else "你是排障 Repairer。必须用工具调查；SOLVED 只能通过 ticket_conclude，且须先 health_recheck=PASS。不要改 backend。"
            )
            loop_result = run_tool_loop(
                system=system,
                user=prompt,
                tools=tool_specs(role),
                execute=runtime.execute,
                complete=lambda **kwargs: deepseek_complete(token=auth_token, **kwargs),
                max_turns=self.max_turns,
                on_event=on_event,
            )
            conclusion = loop_result.get("conclusion") if isinstance(loop_result.get("conclusion"), dict) else None
            result = None
            if conclusion and conclusion.get("ok"):
                result = str(conclusion.get("status") or "").upper()
            if not result:
                result = self._parse_result(str(loop_result.get("text") or ""))
            log_handle.write(f"\nTICKET_RESULT: {result or 'FAILED'}\n")
            log_handle.flush()
            if result not in _RESULT_STATUSES:
                tail = _mask_line((loop_result.get("text") or "")[-1500:])
                self.ticket_service.record_result(
                    ticket_id,
                    status="FAILED",
                    diagnosis=tail or None,
                    error_message="排障无有效结果或异常退出",
                )
                self._notify_need_human(ticket, run_ctx, "自动排障失败（无有效结果），需人工介入", tail[-800:])
                return
            final_status, extra = self._finalize_agent_result(ticket, result)
            gov_status = final_status
            diagnosis = _mask_line((loop_result.get("text") or extra or "")[:_CONCLUSION_MAX_CHARS])
            if extra:
                diagnosis = ((diagnosis or "") + "\n" + extra).strip()
            if final_status == "SOLVED":
                self.ticket_service.record_result(
                    ticket_id, status="SOLVED", diagnosis=diagnosis or "健康复检 PASS"
                )
                logger.info("[AutoRepair] 工单 %s 排障成功（健康复检 PASS）", ticket_code)
                return
            self.ticket_service.record_result(
                ticket_id,
                status=final_status,
                diagnosis=diagnosis or "判定需人工介入",
            )
            self._notify_need_human(ticket, run_ctx, extra or "自动排障判定需人工介入", (diagnosis or "")[-1200:])
        except Exception:
            logger.exception("[AutoRepair] loop 收尾异常 ticket=%s", ticket_code)
            try:
                self.ticket_service.record_result(ticket_id, status="FAILED", error_message="loop 收尾异常")
            except Exception:
                pass
        finally:
            try:
                log_handle.close()
            except Exception:
                pass
            try:
                self._shutdown_browser(ticket)
            except Exception:
                logger.exception("[AutoRepair] 关闭 CDP 调试浏览器失败 ticket=%s", ticket_code)
            try:
                self._apply_script_governance(ticket, run_ctx, gov_status)
            except Exception:
                logger.exception("[AutoRepair] 脚本备份/回滚失败 ticket=%s", ticket_code)
            try:
                self._release_profile_lock(run_ctx)
            except Exception:
                logger.exception("[AutoRepair] 释放目录锁失败 ticket=%s", ticket_code)
            self._slot.release()

    def _wait_process(self, proc: subprocess.Popen) -> str:
        """轮询等待子进程结束，超时强杀。返回 'ok' 或 'timeout'。"""
        deadline = time.monotonic() + self.max_seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return "ok"
            time.sleep(1)
        # 超时：强制杀进程树
        try:
            self._kill_tree(proc.pid)
        except Exception:
            logger.exception("[AutoRepair] 超时杀 claude 进程失败 pid=%s", proc.pid)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        return "timeout"

    # ── 通知 / 关端口 ──

    def _notify_need_human(
        self, ticket: dict[str, Any], run_ctx: dict[str, Any], reason: str, diagnosis: str
    ) -> None:
        try:
            shop = ticket.get("shop_name") or run_ctx.get("shop_name") or "-"
            send_feishu_notification(
                title=f"⚠️ 自动排障需人工介入：{shop}",
                message=reason,
                fields={
                    "渠道": ticket.get("channel") or "-",
                    "店铺": shop,
                    "工单号": ticket.get("ticket_code") or "-",
                    "任务": run_ctx.get("health_task_name") or ticket.get("health_task_code") or "-",
                    "端口": str(ticket.get("cdp_port") or "-"),
                    "诊断": (diagnosis or "")[:600],
                },
            )
        except Exception:
            logger.exception("[AutoRepair] 飞书告警发送失败")

    def _shutdown_browser(self, ticket: dict[str, Any]) -> None:
        """排障结束（含 SOLVED）关闭该 CDP 调试浏览器，避免残留占用。失败只告警。"""
        port = ticket.get("cdp_port")
        if not port or str(ticket.get("kind") or "") == "cookie_sync":
            return
        try:
            kill_chrome_on_port(int(port))
            logger.info("[AutoRepair] 已关闭 CDP 调试浏览器 port=%s", port)
        except Exception:
            logger.exception("[AutoRepair] 关闭 CDP 调试浏览器失败 port=%s", port)

    def _fail_now(
        self, ticket: dict[str, Any], run_ctx: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """唤起前失败：置工单 FAILED（终态）并飞书告警，避免工单永远停在 PENDING。"""
        ticket_id = int(ticket["id"])
        try:
            self.ticket_service.record_result(ticket_id, status="FAILED", error_message=reason)
        except Exception:
            logger.exception("[AutoRepair] 置 FAILED 失败")
        try:
            self._notify_need_human(ticket, run_ctx, reason, "")
        except Exception:
            pass
        return {
            "dispatched": False,
            "reason": reason,
            "ticket_id": ticket_id,
            "ticket_code": ticket.get("ticket_code"),
        }

    # ── 工具 ──

    @staticmethod
    def _use_cli_compat(environ: Mapping[str, str] | None = None) -> bool:
        raw = ((environ or os.environ).get("AUTO_REPAIR_USE_CLI") or "").strip().lower()
        return raw in {"1", "true", "yes"}

    def _resolve_claude(self) -> str | None:
        if self._claude_path is not None:
            return self._claude_path if self._claude_path is not False else None
        resolved: str | None = None
        try:
            for name in _CLAUDE_BINARIES:
                resolved = shutil.which(name)
                if resolved:
                    break
        except Exception:
            resolved = None
        self._claude_path = resolved or False
        return resolved

    def _build_command(self, claude: str, prompt: str) -> list[str]:
        base = [
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--max-turns",
            str(self.max_turns),
            "-p",
            prompt,
        ]
        suffix = Path(claude).suffix.lower()
        if suffix in {".cmd", ".bat"}:
            # npm 全局 .cmd 包装需要经 cmd 启动；探活确认用 claude.cmd 避开 ExecutionPolicy
            return ["cmd", "/c", claude, *base]
        return [claude, *base]

    @staticmethod
    def _budget_from_environ(environ: Mapping[str, str]) -> tuple[int, int]:
        def _parse(name: str, default: int) -> int:
            raw = (environ.get(name) or "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                return default
            return value if value > 0 else default

        return (
            _parse("AUTO_REPAIR_MAX_TURNS", DEFAULT_MAX_TURNS),
            _parse("AUTO_REPAIR_MAX_SECONDS", DEFAULT_MAX_SECONDS),
        )

    @staticmethod
    def _build_child_env(
        base_env: Mapping[str, str],
        *,
        auth_token: str,
        config_dir: str | Path,
    ) -> dict[str, str]:
        env = {k: v for k, v in base_env.items() if k.lower() not in _PROXY_ENV_NAMES}
        env["ANTHROPIC_BASE_URL"] = DEEPSEEK_ANTHROPIC_BASE_URL
        env["ANTHROPIC_AUTH_TOKEN"] = auth_token
        env["ANTHROPIC_MODEL"] = DEEPSEEK_VISION_MODEL
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = DEEPSEEK_VISION_MODEL
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = DEEPSEEK_VISION_MODEL
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = DEEPSEEK_FLASH_MODEL
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = DEEPSEEK_VISION_MODEL
        env["CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT"] = "1"
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
        # 即便残留系统级代理，也强制 DeepSeek API 直连（吸收 Windows 机上的 NO_PROXY 实践）
        env.pop("no_proxy", None)
        existing_no_proxy = (env.get("NO_PROXY") or "").strip()
        env["NO_PROXY"] = (
            existing_no_proxy.rstrip(",") + ",api.deepseek.com"
            if existing_no_proxy
            else "api.deepseek.com"
        )
        return env

    @staticmethod
    def _resolve_auth_token(environ: Mapping[str, str]) -> str | None:
        for key in ("DEEPSEEK_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            value = (environ.get(key) or "").strip()
            if value:
                return value
        home_raw = (environ.get("USERPROFILE") or environ.get("HOME") or "").strip()
        if not home_raw:
            return None
        settings_path = Path(home_raw) / ".claude" / "settings.json"
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        token = str((data.get("env") or {}).get("ANTHROPIC_AUTH_TOKEN") or "").strip()
        return token or None

    @staticmethod
    def _ensure_isolated_config(config_dir: Path) -> Path:
        config_dir.mkdir(parents=True, exist_ok=True)
        payload = {"model": DEEPSEEK_VISION_MODEL, "env": {}}
        (config_dir / "settings.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config_dir

    def _finalize_agent_result(
        self, ticket: dict[str, Any], agent_result: str | None
    ) -> tuple[str, str | None]:
        """平台收尾：FAIL/EXCEPTION 的 SOLVED 必须健康复检 PASS；采集单必须采集复检 PASS；RISK 禁止 SOLVED。"""
        issue = str(ticket.get("issue_type") or "FAIL").upper()
        result = (agent_result or "").upper()
        if str(ticket.get("kind") or "") == "cookie_sync":
            if issue == "NO_MAPPING" and result == "SOLVED":
                return "NEED_HUMAN", "无映射禁止 SOLVED"
            if result != "SOLVED":
                return (result if result in _RESULT_STATUSES else "FAILED"), None
            code = str(ticket.get("cookie_sync_task_code") or ticket.get("health_task_code") or "").strip()
            recheck = self._recheck_cookie_sync(code or None)
            if recheck == "PASS":
                return "SOLVED", f"recheck=COOKIE_SYNC_PASS task={code}"
            return "NEED_HUMAN", f"agent 报 SOLVED 但采集复检未通过 recheck={recheck}"
        if issue == "RISK":
            if result == "SOLVED":
                return "NEED_HUMAN", "RISK 工单禁止 SOLVED（只诊断）"
            if result in _RESULT_STATUSES:
                return result, None
            return "FAILED", None
        if result != "SOLVED":
            return (result if result in _RESULT_STATUSES else "FAILED"), None
        code = str(ticket.get("health_task_code") or "").strip()
        recheck = self._recheck_health(code or None)
        if recheck == "PASS":
            return "SOLVED", f"recheck=PASS health_task={code}"
        return "NEED_HUMAN", f"agent 报 SOLVED 但健康复检未通过 recheck={recheck}"

    def _recheck_health(self, health_task_code: str | None) -> str:
        code = (health_task_code or "").strip()
        if not code:
            return "SKIPPED"
        try:
            from app.services.health_task_service import HealthTaskService

            runtime_root = Path(self.logs_root).parent
            svc = HealthTaskService(engine=self.ticket_service.engine, runtime_root=runtime_root)
            result = svc.execute_check(code, follow_up=False)
            status = str(result.get("status") or "").upper()
            return "PASS" if status == "PASS" else "FAIL"
        except Exception:
            logger.exception("[AutoRepair] 健康复检失败 health_task=%s", code)
            return "FAIL"

    def _read_agent_doc(self, *parts: str, max_chars: int = 12000) -> str:
        path = Path(self.project_root).joinpath(*parts)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return f"（未找到 {path.as_posix()}，请先 Read 该路径）\n"
        if len(text) > max_chars:
            return text[:max_chars] + "\n…(截断)\n"
        return text

    def _memory_snippets(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> str:
        chunks = [self._read_agent_doc("docs", "agent", "memory", "项目运转.md", max_chars=4000)]
        shop = str(ticket.get("shop_name") or "").strip()
        if shop and ".." not in shop and "/" not in shop and "\\" not in shop:
            shop_path = Path(self.project_root) / "docs" / "agent" / "memory" / "shops" / f"{shop}.md"
            if shop_path.is_file():
                try:
                    chunks.append(shop_path.read_text(encoding="utf-8")[:3000])
                except OSError:
                    pass
        script_path = str(run_ctx.get("script_path") or ticket.get("script_code") or "")
        stem = Path(script_path).stem
        if stem and stem not in {".", ""}:
            script_mem = Path(self.project_root) / "docs" / "agent" / "memory" / "scripts" / f"{stem}.md"
            if script_mem.is_file():
                try:
                    chunks.append(script_mem.read_text(encoding="utf-8")[:3000])
                except OSError:
                    pass
        return "\n\n".join(chunks)

    def _artifact_dir_for(self, ticket_code: str) -> str:
        return f"runtime/artifacts/{ticket_code}"

    @staticmethod
    def _should_rollback(issue_type: str | None, final_status: str, keep: bool) -> bool:
        if keep:
            return False
        if str(issue_type or "").upper() == "RISK":
            return False
        return str(final_status or "").upper() != "SOLVED"

    def _profile_service(self):
        from app.services.profile_service import ProfileService

        return ProfileService(engine=self.ticket_service.engine, runtime_root=Path(self.logs_root).parent)

    def _acquire_profile_lock(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> None:
        profile_key = str(run_ctx.get("profile_key") or "").strip()
        if not profile_key:
            return
        owner = f"auto-repair:{ticket.get('ticket_code')}"
        steal_run_id = run_ctx.get("steal_run_id")
        steal = str(steal_run_id).strip() if steal_run_id else None
        self._profile_service().acquire_for_auto_repair(profile_key, owner, steal_run_id=steal)
        run_ctx["_lock_owner"] = owner
        run_ctx["_profile_key"] = profile_key

    def _release_profile_lock(self, run_ctx: dict[str, Any]) -> None:
        profile_key = str(run_ctx.get("_profile_key") or run_ctx.get("profile_key") or "").strip()
        owner = str(run_ctx.get("_lock_owner") or "").strip()
        if not profile_key or not owner:
            return
        self._profile_service().unlock_if_owner(profile_key, owner)

    def _governed_script_path(self, script_path: str | None) -> Path | None:
        if not script_path:
            return None
        p = Path(script_path)
        if not p.is_absolute():
            p = Path(self.project_root) / p
        try:
            resolved = p.resolve()
            root = (Path(self.project_root) / "runtime" / "scripts").resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            return None
        return resolved

    def _prepare_script_backup(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> None:
        if str(ticket.get("issue_type") or "").upper() == "RISK":
            return
        src = self._governed_script_path(str(run_ctx.get("script_path") or "") or None)
        raw = str(run_ctx.get("script_path") or "").strip()
        if raw and (src is None or not src.is_file()):
            raise FileNotFoundError(f"脚本文件丢失或不在 runtime/scripts: {raw}")
        if src is None or not src.is_file():
            return
        ticket_code = str(ticket.get("ticket_code") or "unknown")
        backup_dir = Path(self.logs_root).parent / "artifacts" / ticket_code / "scripts_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / src.name
        shutil.copy2(src, dest)
        run_ctx["_backup_path"] = str(dest)
        run_ctx["_script_path_resolved"] = str(src)

    def _apply_script_governance(
        self, ticket: dict[str, Any], run_ctx: dict[str, Any], final_status: str
    ) -> None:
        backup_raw = run_ctx.get("_backup_path")
        src_raw = run_ctx.get("_script_path_resolved")
        if not backup_raw or not src_raw:
            return
        backup = Path(str(backup_raw))
        src = Path(str(src_raw))
        if not backup.is_file():
            return
        ticket_code = str(ticket.get("ticket_code") or "unknown")
        artifact_dir = Path(self.logs_root).parent / "artifacts" / ticket_code
        artifact_dir.mkdir(parents=True, exist_ok=True)
        old = backup.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        new = src.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if src.is_file() else []
        diff_text = "".join(
            difflib.unified_diff(old, new, fromfile=f"backup/{backup.name}", tofile=str(src.name), lineterm="")
        )
        if not diff_text.endswith("\n"):
            diff_text += "\n"
        (artifact_dir / "script.diff").write_text(diff_text or "(no changes)\n", encoding="utf-8")
        keep = bool(run_ctx.get("keep_script_changes"))
        if self._should_rollback(ticket.get("issue_type"), final_status, keep) and src.parent.exists():
            shutil.copy2(backup, src)

    def _recheck_cookie_sync(self, task_code: str | None) -> str:
        code = (task_code or "").strip()
        if not code:
            return "SKIPPED"
        try:
            from app.services.cookie_sync_task_service import CookieSyncTaskService

            svc = CookieSyncTaskService(engine=self.ticket_service.engine)
            result = svc.execute_check(code, follow_up=False)
            status = str(result.get("status") or "").upper()
            return "PASS" if status == "PASS" else "FAIL"
        except Exception:
            logger.exception("[AutoRepair] 采集复检失败 task=%s", code)
            return "ERROR"

    def _build_collector_prompt(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> str:
        code = ticket.get("cookie_sync_task_code") or ticket.get("health_task_code") or "-"
        return (
            "你是 Collector，只处理本采集工单。\n"
            f"- ticket {ticket.get('ticket_code')} kind=cookie_sync issue={ticket.get('issue_type')}\n"
            f"- 任务 {code} / {run_ctx.get('cookie_sync_task_name') or '-'}\n"
            f"- 渠道 {ticket.get('channel')} 店铺 {ticket.get('shop_name')}\n"
            f"- 错误 {(ticket.get('error_message') or '')[:800]}\n"
            "步骤：ticket_pack_get → sync_mapping_get。无映射则 ticket_conclude NEED_HUMAN。"
            "有映射则 sync_dispatch，再 sync_recheck。PASS 才 ticket_conclude SOLVED。"
            "禁止 CDP、改脚本、写映射。"
        )

    def _build_prompt(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> str:
        script_path = run_ctx.get("script_path") or ticket.get("script_code") or "(未知脚本)"
        port = ticket.get("cdp_port") or 9222
        is_risk = (ticket.get("issue_type") or "").upper() == "RISK"
        err = _mask_line((ticket.get("error_message") or "")[:500])
        ticket_code = ticket.get("ticket_code") or "unknown"
        artifacts = self._artifact_dir_for(str(ticket_code))
        screenshot = f"{artifacts}/shot.png"
        inspector_py = (Path(self.project_root) / "tools" / "cdp_inspector.py").resolve()
        inspector = f"python {inspector_py}"
        profile_path = run_ctx.get("profile_path") or "-"
        log_tail = _mask_line((run_ctx.get("log_tail") or "")[:800])
        health_code = ticket.get("health_task_code") or run_ctx.get("health_task_code") or "-"
        sop = self._read_agent_doc("docs", "agent", "SOP-操作手册.md")
        memory = self._memory_snippets(ticket, run_ctx)
        head = (
            f"你是本系统的自动排障维修员（Auto-Repair Worker），有一张自动排障工单需要现场处理。\n"
            f"工单号: {ticket_code}\n"
            f"渠道: {ticket.get('channel') or '-'}\n"
            f"店铺: {ticket.get('shop_name') or '-'}\n"
            f"目标脚本: {script_path}\n"
            f"CDP 调试端口: {port}\n"
            f"失败类型: {ticket.get('issue_type') or 'FAIL'}\n"
            f"错误摘要: {err}\n"
            f"\n## 本单实例包\n"
            f"- ticket_code: {ticket_code}\n"
            f"- health_task_code: {health_code}\n"
            f"- script_path: {script_path}\n"
            f"- profile_path: {profile_path}\n"
            f"- cdp_port: {port}\n"
            f"- artifacts: {artifacts}\n"
            f"- ticket_dir: {run_ctx.get('ticket_dir') or artifacts}\n"
            f"- screenshot: {screenshot}\n"
            f"- scripts_backup: {artifacts}/scripts_backup/\n"
            f"- fail_log_tail: {log_tail or '-'}\n"
            f"\n只处理本单 ticket_code={ticket_code}。"
            f"禁止查询、列出、切换或处理其它工单/其它店铺/其它脚本；"
            f"禁止扫描 auto_repair_ticket 表或其它 ticket_code。"
            f"若发现其它 RUNNING 工单，忽略并继续本单。\n"
            f"\n平台会强制对绑定健康检测任务做复检：只有复检 PASS 才算 SOLVED。"
            f"你输出的 TICKET_RESULT: SOLVED 只是候选，未复检通过不会关单。"
            f"非 RISK 工单改脚本前平台已备份；复检未 PASS 将回滚脚本。\n"
            f"\n严格按以下 SOP 处理，全程真实探查、严禁凭空猜测。\n"
            f"\n## 操作手册（SOP）\n{sop}\n"
            f"## 项目记忆\n{memory}\n"
        )
        if is_risk:
            steps = (
                f"1. 探查现场：运行 {inspector} --port {port} "
                f"--action inspect --screenshot {screenshot}\n"
                f"2. RISK 风控工单——只诊断判级，不做任何修改与重试：判断当前是否确为人机验证"
                f"（滑块/拼图/短信/扫码/设备验证）或疑似封禁/风控页。\n"
                f"3. 结论（RISK 工单允许的唯一输出动作）：\n"
                f"   - 确认人机验证/疑似封禁 → 输出 TICKET_RESULT: NEED_HUMAN 并说明风控类型；\n"
                f"   - 页面无风控迹象（疑历史误报）→ 仍输出 TICKET_RESULT: NEED_HUMAN 并说明依据，保持保守。\n"
                f"4. RISK 工单严禁：点击消除任何弹窗、重跑目标脚本、任何写操作与尝试自动过验。禁止输出 SOLVED。\n"
            )
        else:
            steps = (
                f"1. 探查现场：运行 {inspector} --port {port} "
                f"--action inspect --screenshot {screenshot}\n"
                f"2. 分析阻碍：根据当前 URL 与可见弹窗/遮罩，判断是运营推广浮层、协议/组织更新，"
                f"还是人机验证（滑块/拼图/短信/扫码/疑似封禁）。\n"
                f"3. 安全红线（最高优先，违反即失败）：\n"
                f"   - 确认人机验证或疑似封禁：立即停止，严禁尝试绕过或反复点击，直接判 NEED_HUMAN。\n"
                f"   - 严禁修改 backend/app/core/ 底座、数据库结构，严禁删除 user_data_dir，严禁终止正常后台服务。\n"
                f"4. 常规遮罩/弹窗：用 {inspector} --port {port} --action click --selector \"CSS选择器\" 单步关闭后，"
                f"重跑验证：python {script_path} --cdp-port {port} --skip-db\n"
            )
        tail = (
            f"5. 收尾（必须）：在回复末尾输出一行含 TICKET_RESULT 的机器可读结果"
            f"（可写在列表/加粗/反引号中，但必须出现完整前缀 TICKET_RESULT:），"
            f"格式严格为：\n"
            f"   TICKET_RESULT: SOLVED       （你认为已修好，仅非 RISK 可输出；平台仍会强制复检）\n"
            f"   TICKET_RESULT: NEED_HUMAN    （人机验证/无法确认/需人工）\n"
            f"   并在结果行之前用 2-4 行简述：阻挡原因、处理动作、修复结果。\n"
            f"\n预算：单次排障最多 {self.max_turns} 轮工具调用即须给出结论，不要扩大修改范围。"
        )
        return head + steps + tail

    def _prepare_log_file(self, ticket_code: str) -> Path:
        # 运行时日志目录（dispatcher 自身落盘）
        base = self.logs_root / "auto_repair"
        base.mkdir(parents=True, exist_ok=True)
        # claude 在 project_root 下运行，其截图等相对路径写 project_root/logs/auto_repair
        try:
            (self.project_root / "logs" / "auto_repair").mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return base / f"{ticket_code}.log"

    @staticmethod
    def _read_log(log_file: Path) -> str:
        try:
            return log_file.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    @staticmethod
    def _parse_result(text: str) -> str | None:
        if not text:
            return None
        matches = _RESULT_PATTERN.findall(text)
        return matches[-1].upper() if matches else None

    @staticmethod
    def _kill_tree(pid: int) -> None:
        if not pid:
            return
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )


def reap_stuck_auto_repair_tickets(
    engine,
    runtime_root: Path,
    *,
    now: datetime | None = None,
    running_timeout_seconds: int | None = None,
    pending_age_seconds: int = 300,
) -> dict[str, int]:
    """辅路径：RUNNING 超时强杀并 FAILED；过久 PENDING 再尝试唤起。"""
    from app.services.auto_repair_ticket_service import beijing_now

    runtime_root = Path(runtime_root)
    clock = now or beijing_now()
    timeout = running_timeout_seconds if running_timeout_seconds is not None else DEFAULT_MAX_SECONDS + 60
    ticket_service = AutoRepairTicketService(engine=engine)
    failed = 0
    retried = 0

    for ticket in ticket_service.list_stale_running(clock - timedelta(seconds=timeout)):
        code = ticket.get("ticket_code") or ""
        pid_path = runtime_root / "artifacts" / str(code) / "agent.pid"
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = 0
        if pid:
            try:
                AgentRepairDispatcher._kill_tree(pid)
            except Exception:
                logger.exception("[AutoRepair] 卡死工单杀进程失败 ticket=%s pid=%s", code, pid)
        ticket_service.record_result(
            int(ticket["id"]),
            status="FAILED",
            error_message="RUNNING 超时未收口，调度补扫强制终止",
        )
        try:
            port = int(ticket.get("cdp_port") or 0)
            if port:
                kill_chrome_on_port(port)
        except Exception:
            pass
        failed += 1

    for ticket in ticket_service.list_stale_pending(clock - timedelta(seconds=pending_age_seconds)):
        try:
            result = trigger_auto_repair(
                engine,
                channel=str(ticket.get("channel") or ""),
                shop_name=ticket.get("shop_name"),
                cdp_port=int(ticket.get("cdp_port") or 9222),
                script_code=ticket.get("script_code"),
                health_task_code=ticket.get("health_task_code"),
                script_run_id=ticket.get("script_run_id"),
                issue_type=str(ticket.get("issue_type") or "FAIL"),
                error_message=ticket.get("error_message"),
            )
            if result.get("dispatched"):
                retried += 1
        except Exception:
            logger.exception("[AutoRepair] PENDING 补扫唤起失败 ticket=%s", ticket.get("ticket_code"))

    return {"failed": failed, "retried": retried}


def trigger_auto_repair(
    engine,
    *,
    channel: str,
    shop_name: str | None = None,
    cdp_port: int = 9222,
    script_code: str | None = None,
    script_path: str | None = None,
    health_task_code: str | None = None,
    health_task_name: str | None = None,
    script_run_id: int | None = None,
    issue_type: str = "FAIL",
    error_message: str | None = None,
    profile_key: str | None = None,
    profile_path: str | None = None,
    steal_run_id: str | None = None,
) -> dict[str, Any]:
    """一次自动排障的完整触发：建单/复用 → 节流校验 → 唤起（后台收尾）。

    供健康检测/脚本运行收尾处调用；不抛异常，失败均有终态与告警。
    """
    from app.core.config import get_settings

    cfg = get_settings()
    try:
        ticket_service = AutoRepairTicketService(engine=engine)
        ticket = ticket_service.create_or_reuse(
            channel=channel,
            shop_name=shop_name,
            cdp_port=cdp_port,
            script_code=script_code,
            health_task_code=health_task_code,
            script_run_id=script_run_id,
            issue_type=issue_type,
            error_message=error_message,
        )
    except Exception:
        logger.exception("[AutoRepair] 自动排障建单失败 channel=%s shop=%s", channel, shop_name)
        return {"dispatched": False, "reason": "建单失败", "ticket_id": None, "ticket_code": None}

    # 节流按 (channel, shop_name) 店铺维度判定（REQ-011），与工单生命周期无关
    verdict = ticket_service.evaluate_dispatch(channel, shop_name)
    if not verdict["ok"]:
        logger.info(
            "[AutoRepair] 跳过唤起 channel=%s shop=%s ticket=%s reason=%s",
            channel,
            shop_name,
            ticket["ticket_code"],
            verdict["reason"],
        )
        return {
            "dispatched": False,
            "reason": verdict["reason"],
            "ticket_id": ticket["id"],
            "ticket_code": ticket["ticket_code"],
            "ticket_status": ticket["status"],
        }

    max_turns, max_seconds = AgentRepairDispatcher._budget_from_environ(os.environ)
    dispatcher = AgentRepairDispatcher(
        ticket_service=ticket_service,
        project_root=cfg.deploy_root,
        logs_root=cfg.runtime_root / "logs",
        max_turns=max_turns,
        max_seconds=max_seconds,
    )
    run_ctx = {
        "script_path": script_path,
        "health_task_name": health_task_name or health_task_code,
        "shop_name": shop_name,
        "health_task_code": health_task_code,
        "profile_key": profile_key,
        "profile_path": profile_path,
        "steal_run_id": steal_run_id,
    }
    result = dispatcher.dispatch(ticket, run_ctx)
    result["ticket_status"] = "RUNNING" if result.get("dispatched") else ticket.get("status")
    return result


def trigger_cookie_sync_repair(
    engine,
    *,
    channel: str,
    shop_name: str | None = None,
    cookie_sync_task_code: str | None = None,
    cookie_sync_task_name: str | None = None,
    issue_type: str = "RECHECK_FAIL",
    error_message: str | None = None,
) -> dict[str, Any]:
    """采集失败另立 cookie_sync 工单并唤起 Collector loop。"""
    from app.core.config import get_settings

    cfg = get_settings()
    try:
        ticket_service = AutoRepairTicketService(engine=engine)
        ticket = ticket_service.create_or_reuse(
            channel=channel,
            shop_name=shop_name,
            cdp_port=9222,
            health_task_code=cookie_sync_task_code,
            issue_type=issue_type,
            error_message=error_message,
            kind="cookie_sync",
            cookie_sync_task_code=cookie_sync_task_code,
        )
    except Exception:
        logger.exception("[AutoRepair] 采集工单建单失败 channel=%s shop=%s", channel, shop_name)
        return {"dispatched": False, "reason": "建单失败", "ticket_id": None, "ticket_code": None}

    verdict = ticket_service.evaluate_dispatch(channel, shop_name)
    if not verdict["ok"]:
        logger.info(
            "[AutoRepair] 跳过采集唤起 channel=%s shop=%s ticket=%s reason=%s",
            channel,
            shop_name,
            ticket["ticket_code"],
            verdict["reason"],
        )
        return {
            "dispatched": False,
            "reason": verdict["reason"],
            "ticket_id": ticket["id"],
            "ticket_code": ticket["ticket_code"],
            "ticket_status": ticket["status"],
        }

    max_turns, max_seconds = AgentRepairDispatcher._budget_from_environ(os.environ)
    dispatcher = AgentRepairDispatcher(
        ticket_service=ticket_service,
        project_root=cfg.deploy_root,
        logs_root=cfg.runtime_root / "logs",
        max_turns=max_turns,
        max_seconds=max_seconds,
    )
    run_ctx = {
        "cookie_sync_task_code": cookie_sync_task_code,
        "cookie_sync_task_name": cookie_sync_task_name or cookie_sync_task_code,
        "shop_name": shop_name,
        "health_task_code": cookie_sync_task_code,
    }
    result = dispatcher.dispatch(ticket, run_ctx)
    result["ticket_status"] = "RUNNING" if result.get("dispatched") else ticket.get("status")
    return result
