"""自动排障过程事件（给前端时间线）。不落新表，从日志/产物即时组装。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TICKET_RESULT_LINE = re.compile(
    r"^[ \t]*TICKET_RESULT[ \t]*[:：]",
    re.IGNORECASE,
)
_RECHECK_IN_DIAG = re.compile(r"recheck=([A-Z]+)")


def extract_cli_json(log_text: str) -> dict[str, Any] | None:
    """从 CLI 日志里取出最后一个 result/usage JSON（前面可能有 unrecognized_model 行）。"""
    if not log_text:
        return None
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    idx = log_text.find("{")
    while idx != -1:
        try:
            obj, _end = decoder.raw_decode(log_text, idx)
        except json.JSONDecodeError:
            idx = log_text.find("{", idx + 1)
            continue
        if isinstance(obj, dict) and (
            "usage" in obj or "result" in obj or obj.get("type") == "result"
        ):
            found = obj
        idx = log_text.find("{", idx + 1)
    return found


def normalize_usage(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    usage_obj = payload.get("usage")
    raw: dict[str, Any] = usage_obj if isinstance(usage_obj, dict) else {}
    input_tokens = raw.get("input_tokens", raw.get("prompt_tokens"))
    output_tokens = raw.get("output_tokens", raw.get("completion_tokens"))
    cache_read = raw.get("cache_read_input_tokens", raw.get("cache_read_tokens"))
    cache_write = raw.get("cache_creation_input_tokens", raw.get("cache_write_tokens"))
    has_usage = any(v is not None for v in (input_tokens, output_tokens, payload.get("total_cost_usd"), payload.get("num_turns")))
    if not has_usage:
        return None
    inp = int(input_tokens or 0)
    out = int(output_tokens or 0)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": int(cache_read or 0),
        "cache_write_tokens": int(cache_write or 0),
        "total_tokens": inp + out,
        "total_cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
        "num_turns": payload.get("num_turns"),
        "model": payload.get("model"),
    }


def _text_from_cli_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    result = payload.get("result")
    if isinstance(result, str) and result.strip():
        return result
    if isinstance(result, dict):
        nested = _text_from_cli_payload(result)
        if nested:
            return nested
    message = payload.get("message")
    blob: Any = message if isinstance(message, dict) else payload
    content = blob.get("content") if isinstance(blob, dict) else None
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        joined = "\n".join(chunks).strip()
        return joined or None
    return None


def unwrap_cli_log(log_text: str) -> tuple[str, dict[str, Any] | None]:
    payload = extract_cli_json(log_text)
    usage = normalize_usage(payload)
    if usage:
        usage = {**usage, "source": usage.get("source") or "cli_json"}
    body = _text_from_cli_payload(payload)
    if body:
        return body, usage
    return log_text or "", usage


def extract_usage_from_session_jsonl(path: Path) -> dict[str, Any] | None:
    """从 Claude Code 会话 jsonl 汇总 usage（无 type=result 信封时按 assistant 轮次加总）。"""
    total_in = total_out = cache_r = cache_w = 0
    turns = 0
    model: str | None = None
    result_usage: dict[str, Any] | None = None
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            kind = str(obj.get("type") or "")
            if kind == "result":
                parsed = normalize_usage(obj)
                if parsed:
                    result_usage = {
                        **parsed,
                        "source": "session_jsonl",
                        "session_file": path.name,
                    }
                continue
            if kind != "assistant":
                continue
            message = obj.get("message")
            msg: dict[str, Any] = message if isinstance(message, dict) else {}
            raw = obj.get("usage") if isinstance(obj.get("usage"), dict) else None
            if raw is None:
                maybe_usage = msg.get("usage")
                raw = maybe_usage if isinstance(maybe_usage, dict) else None
            if not isinstance(raw, dict):
                continue
            turns += 1
            total_in += int(raw.get("input_tokens") or 0)
            total_out += int(raw.get("output_tokens") or 0)
            cache_r += int(raw.get("cache_read_input_tokens") or raw.get("cache_read_tokens") or 0)
            cache_w += int(raw.get("cache_creation_input_tokens") or raw.get("cache_write_tokens") or 0)
            found_model = msg.get("model") or obj.get("model") or model
            model = str(found_model) if found_model else model
    if result_usage:
        return result_usage
    if turns == 0:
        return None
    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cache_read_tokens": cache_r,
        "cache_write_tokens": cache_w,
        "total_tokens": total_in + total_out,
        "num_turns": turns,
        "model": model,
        "source": "session_jsonl",
        "session_file": path.name,
    }


def find_session_jsonl_for_ticket(ticket_code: str, config_dirs: list[Path]) -> Path | None:
    if not ticket_code:
        return None
    for root in config_dirs:
        root = Path(root)
        if not root.is_dir():
            continue
        hits: list[Path] = []
        try:
            candidates = root.rglob("*.jsonl")
        except OSError:
            continue
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if ticket_code in text:
                hits.append(path)
        if hits:
            return max(hits, key=lambda p: p.stat().st_mtime)
    return None


def collect_usage_from_claude_sessions(ticket_code: str, config_dirs: list[Path]) -> dict[str, Any] | None:
    path = find_session_jsonl_for_ticket(ticket_code, config_dirs)
    if path is None:
        return None
    return extract_usage_from_session_jsonl(path)


def _session_config_dirs(runtime_root: Path) -> list[Path]:
    dirs = [Path(runtime_root) / "cache" / "claude_agent"]
    home = Path.home() / ".claude"
    if home not in dirs:
        dirs.append(home)
    return dirs


def format_usage_text(usage: dict[str, Any]) -> str:
    parts = [
        f"input {usage.get('input_tokens', 0)}",
        f"output {usage.get('output_tokens', 0)}",
        f"total {usage.get('total_tokens', 0)}",
    ]
    cache_r = int(usage.get("cache_read_tokens") or 0)
    cache_w = int(usage.get("cache_write_tokens") or 0)
    if cache_r or cache_w:
        parts.append(f"cache_read {cache_r}")
        parts.append(f"cache_write {cache_w}")
    if usage.get("num_turns") is not None:
        parts.append(f"turns {usage['num_turns']}")
    if usage.get("duration_ms") is not None:
        parts.append(f"{int(usage['duration_ms']) / 1000:.1f}s")
    if usage.get("model"):
        parts.append(str(usage["model"]))
    cost = usage.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        parts.append(f"${cost:.6f}")
    return " · ".join(parts)


def _mask(text: str) -> str:
    if not text:
        return text
    try:
        from app.services.health_task_service import HealthTaskService

        return HealthTaskService._mask_sensitive(text)
    except Exception:
        return text


def build_agent_events(
    *,
    log_text: str = "",
    diff_text: str | None = None,
    screenshot_rel: str | None = None,
    recheck: str | None = None,
    status: str | None = None,
    usage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    body, parsed_usage = unwrap_cli_log(log_text)
    usage = usage or parsed_usage
    tool_lines: list[str] = []
    think_lines: list[str] = []
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[claude-code:") or "cdp_inspector.py" in line or stripped.startswith("python tools/"):
            tool_lines.append(line)
        elif _TICKET_RESULT_LINE.match(line):
            continue
        else:
            think_lines.append(line)
    if tool_lines:
        events.append({"type": "tool_call", "text": _mask("\n".join(tool_lines)[:2000])})
    think = _mask("\n".join(think_lines).strip())
    if think:
        events.append({"type": "think", "text": think[:8000]})
    if screenshot_rel:
        events.append({"type": "screenshot", "text": screenshot_rel, "path": screenshot_rel})
    if diff_text and diff_text.strip() and diff_text.strip() != "(no changes)":
        events.append({"type": "script_diff", "text": diff_text[:20000]})
    if recheck:
        events.append({"type": "recheck", "text": recheck})
    if status:
        events.append({"type": "status", "text": status})
    if usage:
        events.append({"type": "usage", "text": format_usage_text(usage), "usage": usage})
    return events


def collect_ticket_events(runtime_root: Path, ticket: dict[str, Any]) -> list[dict[str, Any]]:
    code = str(ticket.get("ticket_code") or "")
    runtime_root = Path(runtime_root)
    log_path = runtime_root / "logs" / "auto_repair" / f"{code}.log"
    art = runtime_root / "artifacts" / code
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log_text = ""
    try:
        diff_text = (art / "script.diff").read_text(encoding="utf-8", errors="replace")
    except OSError:
        diff_text = None
    shot = art / "shot.png"
    screenshot_rel = f"runtime/artifacts/{code}/shot.png" if shot.is_file() else None
    diagnosis = str(ticket.get("diagnosis") or "")
    m = _RECHECK_IN_DIAG.search(diagnosis)
    recheck = m.group(1) if m else None
    usage = collect_ticket_usage(runtime_root, code, log_text=log_text)
    return build_agent_events(
        log_text=log_text,
        diff_text=diff_text,
        screenshot_rel=screenshot_rel,
        recheck=recheck,
        status=ticket.get("status"),
        usage=usage,
    )


def collect_ticket_usage(runtime_root: Path, ticket_code: str, *, log_text: str | None = None) -> dict[str, Any] | None:
    runtime_root = Path(runtime_root)
    art = runtime_root / "artifacts" / ticket_code / "usage.json"
    try:
        data = json.loads(art.read_text(encoding="utf-8"))
        if isinstance(data, dict) and (data.get("input_tokens") is not None or data.get("total_tokens") is not None):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    if log_text is None:
        log_path = runtime_root / "logs" / "auto_repair" / f"{ticket_code}.log"
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = ""
    _body, usage = unwrap_cli_log(log_text or "")
    if usage:
        return usage
    return collect_usage_from_claude_sessions(ticket_code, _session_config_dirs(runtime_root))


def collect_ticket_diff(runtime_root: Path, ticket_code: str) -> str:
    path = Path(runtime_root) / "artifacts" / ticket_code / "script.diff"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
