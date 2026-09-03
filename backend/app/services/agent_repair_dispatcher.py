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

import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.services.auto_repair_ticket_service import AutoRepairTicketService
from app.services.chrome_utils import kill_chrome_on_port
from app.services.notification_service import send_feishu_notification

logger = logging.getLogger(__name__)

# 机器可读结果行：锚定行首 + 只认 TICKET_RESULT 前缀（避免正文/tool 输出的
# 裸 "result:" 字样误命中；prompt 会回显示例行，必须行首锚定防把示例当结论）
_RESULT_PATTERN = re.compile(
    r"^[ \t]*TICKET_RESULT[ \t]*[:：][ \t]*(SOLVED|NEED_HUMAN|FAILED)",
    re.IGNORECASE | re.MULTILINE,
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
        max_turns: int = 4,
        max_seconds: int = 120,
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
        try:
            claude = self._resolve_claude()
            if claude is None:
                self._slot.release()
                return self._fail_now(ticket, run_ctx, "本机未找到 claude CLI（@anthropic-ai/claude-code），无法唤起排障")
            prompt = self._build_prompt(ticket, run_ctx)
            log_file = self._prepare_log_file(ticket_code)
            cmd = self._build_command(claude, prompt)
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=open(log_file, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:  # Popen 等异常：回收许可并置终态
            self._slot.release()
            logger.exception("[AutoRepair] 唤起 claude 失败 ticket=%s", ticket_code)
            return self._fail_now(ticket, run_ctx, f"唤起 claude 失败: {exc}")

        # 进程已起：先落 RUNNING + 店铺维度冷却/预算记账，再后台收尾
        try:
            self.ticket_service.mark_dispatched(
                channel=ticket.get("channel") or "",
                shop_name=ticket.get("shop_name"),
                ticket_id=ticket_id,
            )
        except Exception:
            logger.exception("[AutoRepair] 标记 RUNNING 失败 ticket=%s", ticket_code)

        try:
            threading.Thread(
                target=self._reap,
                args=(proc, ticket, run_ctx, log_file),
                name=f"auto-repair-{ticket_code}",
                daemon=True,
            ).start()
        except Exception:
            # 线程创建失败（极罕见）：杀进程 + 置终态并 release
            try:
                self._kill_tree(proc.pid)
            except Exception:
                pass
            self._slot.release()
            logger.exception("[AutoRepair] 收尾线程创建失败 ticket=%s", ticket_code)
            return self._fail_now(ticket, run_ctx, "收尾线程创建失败")

        logger.info("[AutoRepair] 已唤起 claude 排障 ticket=%s pid=%s", ticket_code, proc.pid)
        return {
            "dispatched": True,
            "reason": "ok",
            "ticket_id": ticket_id,
            "ticket_code": ticket_code,
            "pid": proc.pid,
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
        try:
            status = self._wait_process(proc)  # 'ok' 或 'timeout'
            text = self._read_log(log_file)
            result = self._parse_result(text)

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

            if result == "SOLVED":
                diagnosis = _mask_line(text[-_CONCLUSION_MAX_CHARS:])
                self.ticket_service.record_result(ticket_id, status="SOLVED", diagnosis=diagnosis or "claude 未输出诊断说明")
                logger.info("[AutoRepair] 工单 %s 排障成功", ticket_code)
                return

            # NEED_HUMAN
            diagnosis = _mask_line(text[-_CONCLUSION_MAX_CHARS:])
            self.ticket_service.record_result(ticket_id, status="NEED_HUMAN", diagnosis=diagnosis or "claude 判定需人工介入")
            self._shutdown_browser(ticket)
            self._notify_need_human(ticket, run_ctx, "自动排障判定需人工介入（人机验证/无法确认）", diagnosis[-1200:])
        except Exception:
            logger.exception("[AutoRepair] 收尾处理异常 ticket=%s", ticket_code)
            try:
                self.ticket_service.record_result(ticket_id, status="FAILED", error_message="收尾处理异常")
            except Exception:
                pass
            try:
                self._shutdown_browser(ticket)
            except Exception:
                pass
        finally:
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
        """修不动时关闭该 CDP 调试浏览器，避免残留占用。失败只告警。"""
        port = ticket.get("cdp_port")
        if not port:
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

    def _resolve_claude(self) -> str | None:
        if self._claude_path is not None:
            return self._claude_path if self._claude_path is not False else None
        try:
            resolved = shutil.which("claude")
        except Exception:
            resolved = None
        self._claude_path = resolved or False
        return resolved

    def _build_command(self, claude: str, prompt: str) -> list[str]:
        base = ["-p", prompt, "--max-turns", str(self.max_turns)]
        suffix = Path(claude).suffix.lower()
        if suffix in {".cmd", ".bat"}:
            # npm 全局 .cmd 包装需要经 cmd 启动
            return ["cmd", "/c", claude, *base]
        return [claude, *base]

    def _build_prompt(self, ticket: dict[str, Any], run_ctx: dict[str, Any]) -> str:
        script_path = run_ctx.get("script_path") or ticket.get("script_code") or "(未知脚本)"
        port = ticket.get("cdp_port") or 9222
        is_risk = (ticket.get("issue_type") or "").upper() == "RISK"
        err = _mask_line((ticket.get("error_message") or "")[:500])
        head = (
            f"你是本系统的自动排障维修员（Auto-Repair Worker），有一张自动排障工单需要现场处理。\n"
            f"工单号: {ticket.get('ticket_code')}\n"
            f"渠道: {ticket.get('channel') or '-'}\n"
            f"店铺: {ticket.get('shop_name') or '-'}\n"
            f"目标脚本: {script_path}\n"
            f"CDP 调试端口: {port}\n"
            f"失败类型: {ticket.get('issue_type') or 'FAIL'}\n"
            f"错误摘要: {err}\n"
            f"\n严格按以下 SOP 处理，全程真实探查、严禁凭空猜测。\n"
        )
        if is_risk:
            steps = (
                f"1. 探查现场：运行 python .claude/tools/cdp_inspector.py --port {port} "
                f"--action inspect --screenshot logs/auto_repair_{ticket.get('ticket_code')}.png\n"
                f"2. RISK 风控工单——只诊断判级，不做任何修改与重试：判断当前是否确为人机验证"
                f"（滑块/拼图/短信/扫码/设备验证）或疑似封禁/风控页。\n"
                f"3. 结论（RISK 工单允许的唯一输出动作）：\n"
                f"   - 确认人机验证/疑似封禁 → 输出 TICKET_RESULT: NEED_HUMAN 并说明风控类型；\n"
                f"   - 页面无风控迹象（疑历史误报）→ 仍输出 TICKET_RESULT: NEED_HUMAN 并说明依据，保持保守。\n"
                f"4. RISK 工单严禁：点击消除任何弹窗、重跑目标脚本、任何写操作与尝试自动过验。\n"
            )
        else:
            steps = (
                f"1. 探查现场：运行 python .claude/tools/cdp_inspector.py --port {port} "
                f"--action inspect --screenshot logs/auto_repair_{ticket.get('ticket_code')}.png\n"
                f"2. 分析阻碍：根据当前 URL 与可见弹窗/遮罩，判断是运营推广浮层、协议/组织更新，"
                f"还是人机验证（滑块/拼图/短信/扫码/疑似封禁）。\n"
                f"3. 安全红线（最高优先，违反即失败）：\n"
                f"   - 确认人机验证或疑似封禁：立即停止，严禁尝试绕过或反复点击，直接判 NEED_HUMAN。\n"
                f"   - 严禁修改 backend/app/core/ 底座、数据库结构，严禁删除 user_data_dir，严禁终止正常后台服务。\n"
                f"4. 常规遮罩/弹窗：用 cdp_inspector 的 click 动作单步关闭对应按钮后，"
                f"重跑验证：python {script_path} --cdp-port {port} --skip-db\n"
            )
        tail = (
            f"5. 收尾（必须）：在回复末尾单独输出一行机器可读结果，行首必须是 TICKET_RESULT，"
            f"格式严格为：\n"
            f"   TICKET_RESULT: SOLVED       （问题已消除/脚本重跑通过，仅非 RISK 可输出）\n"
            f"   TICKET_RESULT: NEED_HUMAN    （人机验证/无法确认/需人工）\n"
            f"   并在结果行之前用 2-4 行简述：阻挡原因、处理动作、修复结果。\n"
            f"\n预算：单次排障最多 4 轮工具调用即须给出结论，不要扩大修改范围。"
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

    dispatcher = AgentRepairDispatcher(
        ticket_service=ticket_service,
        project_root=cfg.deploy_root,
        logs_root=cfg.runtime_root / "logs",
    )
    run_ctx = {
        "script_path": script_path,
        "health_task_name": health_task_name or health_task_code,
        "shop_name": shop_name,
    }
    result = dispatcher.dispatch(ticket, run_ctx)
    # 通知调用方工单当前状态：唤起成功即 RUNNING（供"是否兜底清理现场浏览器"决策）
    result["ticket_status"] = "RUNNING" if result.get("dispatched") else ticket.get("status")
    return result
