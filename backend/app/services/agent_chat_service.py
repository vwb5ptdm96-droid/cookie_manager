"""网页 Agent 对话：只问答、不改脚本。排障执行仍走 dispatcher。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from app.core.errors import AppError
from app.services.agent_repair_dispatcher import AgentRepairDispatcher
from app.services.auto_repair_ticket_service import AutoRepairTicketService

logger = logging.getLogger(__name__)

BEIJING = timezone(timedelta(hours=8))
CHAT_MAX_TURNS = 8
CHAT_MAX_SECONDS = 120
CHAT_MAX_MESSAGE = 4000
CHAT_HISTORY_LIMIT = 20


def beijing_now() -> datetime:
    return datetime.now(BEIJING).replace(tzinfo=None)


def build_chat_prompt(
    message: str,
    *,
    ticket: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    parts = [
        "你是 Session 维护台的值班 Watcher。只读查询，解释状态。",
        "不要改文件、不要执行脚本、不要开浏览器、不要输出 TICKET_RESULT。",
        "用简体中文短句。数字必须来自工具结果。",
    ]
    if ticket:
        parts.append(
            "当前工单：\n"
            f"- 编号 {ticket.get('ticket_code')}\n"
            f"- 状态 {ticket.get('status')} / {ticket.get('issue_type')}\n"
            f"- 渠道 {ticket.get('channel')} / 店铺 {ticket.get('shop_name')}\n"
            f"- 健康任务 {ticket.get('health_task_code')}\n"
            f"- CDP {ticket.get('cdp_port')}\n"
            f"- 错误 {(ticket.get('error_message') or '')[:500]}\n"
            f"- 诊断 {(ticket.get('diagnosis') or '')[:800]}"
        )
    if history:
        lines = []
        for item in history[-CHAT_HISTORY_LIMIT:]:
            role = "用户" if item.get("role") == "user" else "助手"
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(f"{role}: {text[:800]}")
        if lines:
            parts.append("最近对话：\n" + "\n".join(lines))
    parts.append("用户问题：\n" + (message or "").strip()[:CHAT_MAX_MESSAGE])
    return "\n\n".join(parts)


def chat_dir(runtime_root: Path, ticket_code: str | None) -> Path:
    name = ticket_code or "general"
    path = Path(runtime_root) / "artifacts" / "_agent_chat"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{name}.jsonl"


def load_chat_history(runtime_root: Path, ticket_code: str | None) -> list[dict[str, Any]]:
    path = chat_dir(runtime_root, ticket_code)
    if not path.is_file():
        return []
    items: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("text"):
                items.append(obj)
    except OSError:
        return []
    return items[-80:]


def append_chat(runtime_root: Path, ticket_code: str | None, role: str, text: str) -> dict[str, Any]:
    path = chat_dir(runtime_root, ticket_code)
    row = {
        "role": role,
        "text": text,
        "ts": beijing_now().isoformat(timespec="seconds"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


class AgentChatService:
    def __init__(self, engine: Engine, runtime_root: Path, project_root: Path) -> None:
        self.engine = engine
        self.runtime_root = Path(runtime_root)
        self.project_root = Path(project_root)
        self.tickets = AutoRepairTicketService(engine=engine)

    def ask(self, message: str, ticket_id: int | None = None) -> dict[str, Any]:
        text = (message or "").strip()
        if not text:
            raise AppError("请输入问题", "AGENT_CHAT_EMPTY", status_code=400)
        if len(text) > CHAT_MAX_MESSAGE:
            text = text[:CHAT_MAX_MESSAGE]
        ticket = self.tickets.get_ticket(ticket_id) if ticket_id else None
        if ticket_id and ticket is None:
            raise AppError("自动排障工单不存在", "AUTO_REPAIR_TICKET_NOT_FOUND", status_code=404)
        code = str(ticket.get("ticket_code") or "") if ticket else None
        history = load_chat_history(self.runtime_root, code)
        append_chat(self.runtime_root, code, "user", text)
        prompt = build_chat_prompt(text, ticket=ticket, history=history)
        reply = self._run_loop(prompt, ticket=ticket)
        append_chat(self.runtime_root, code, "assistant", reply)
        return {
            "reply": reply,
            "ticket_id": ticket_id,
            "ticket_code": code,
            "items": load_chat_history(self.runtime_root, code),
        }

    def history(self, ticket_id: int | None = None) -> list[dict[str, Any]]:
        ticket = self.tickets.get_ticket(ticket_id) if ticket_id else None
        code = str(ticket.get("ticket_code") or "") if ticket else None
        return load_chat_history(self.runtime_root, code)

    def _run_loop(self, prompt: str, ticket: dict[str, Any] | None) -> str:
        from app.services.agent_loop import deepseek_complete, run_tool_loop
        from app.services.agent_repair_dispatcher import AgentRepairDispatcher
        from app.services.agent_tools import ToolRuntime, tool_specs

        dispatcher = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
        token = dispatcher._resolve_auth_token(os.environ)
        if not token:
            raise AppError("未配置 DeepSeek API Key，无法对话", "AGENT_CHAT_NO_KEY", status_code=503)
        runtime = ToolRuntime(
            engine=self.engine,
            runtime_root=self.runtime_root,
            project_root=self.project_root,
            role="watcher",
            ticket=ticket,
            run_ctx={},
        )
        try:
            result = run_tool_loop(
                system="Watcher 只读值班。必须用工具取数，禁止改脚本。",
                user=prompt,
                tools=tool_specs("watcher"),
                execute=runtime.execute,
                complete=lambda **kwargs: deepseek_complete(token=token, **kwargs),
                max_turns=CHAT_MAX_TURNS,
            )
        except Exception as exc:
            logger.exception("[AgentChat] loop failed")
            raise AppError(f"Agent 调用失败: {exc}", "AGENT_CHAT_LOOP_FAILED", status_code=502) from exc
        reply = str(result.get("text") or "").strip()
        if not reply:
            raise AppError("Agent 没有返回内容", "AGENT_CHAT_EMPTY_REPLY", status_code=502)
        return reply[:8000]
