"""进程内 tool-calling loop（DeepSeek Anthropic 兼容端）。CLI 不再是主路径。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx

from app.services.agent_repair_dispatcher import DEEPSEEK_ANTHROPIC_BASE_URL, DEEPSEEK_VISION_MODEL

logger = logging.getLogger(__name__)

CompleteFn = Callable[..., dict[str, Any]]
ExecuteFn = Callable[[str, dict[str, Any]], dict[str, Any]]
EventFn = Callable[[str, dict[str, Any]], None]


def deepseek_complete(
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    token: str,
    model: str = DEEPSEEK_VISION_MODEL,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    headers = {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = f"{DEEPSEEK_ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"
    with httpx.Client(trust_env=False, timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("DeepSeek 返回非对象")
    return data


def run_tool_loop(
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    execute: ExecuteFn,
    complete: CompleteFn,
    max_turns: int = 8,
    on_event: EventFn | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    last_text = ""
    for turn in range(max_turns):
        data = complete(system=system, messages=messages, tools=tools)
        content = data.get("content")
        if not isinstance(content, list):
            content = [{"type": "text", "text": str(data.get("content") or "")}]
        stop = str(data.get("stop_reason") or "")
        texts = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        last_text = "\n".join(part for part in texts if part).strip()
        if on_event and last_text:
            on_event("think", {"text": last_text[:4000]})
        tool_uses = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]
        messages.append({"role": "assistant", "content": content})
        if not tool_uses:
            return {"text": last_text, "turns": turn + 1, "stop": stop or "end_turn"}
        results: list[dict[str, Any]] = []
        concluded: dict[str, Any] | None = None
        for use in tool_uses:
            name = str(use.get("name") or "")
            raw_input = use.get("input")
            args = raw_input if isinstance(raw_input, dict) else {}
            if on_event:
                on_event("tool_call", {"name": name, "input": args})
            try:
                output = execute(name, args)
            except Exception as exc:  # 工具失败回填模型，不炸 loop
                logger.exception("[AgentLoop] tool %s failed", name)
                output = {"ok": False, "error": str(exc)[:500]}
            if on_event:
                on_event("tool_result", {"name": name, "output": output})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use.get("id"),
                    "content": json.dumps(output, ensure_ascii=False)[:8000],
                }
            )
            if isinstance(output, dict) and output.get("stop_loop"):
                concluded = output
        messages.append({"role": "user", "content": results})
        if concluded:
            return {
                "text": last_text,
                "turns": turn + 1,
                "stop": "concluded",
                "conclusion": concluded,
            }
    return {"text": last_text, "turns": max_turns, "stop": "max_turns"}
