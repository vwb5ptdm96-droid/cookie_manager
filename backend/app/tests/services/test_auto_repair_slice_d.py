"""Slice D：Agent 事件时间线 + 卡死工单补扫。"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.auto_repair_ticket import AutoRepairTicket
from app.services.agent_event_builder import (
    build_agent_events,
    collect_ticket_events,
    collect_ticket_usage,
    extract_usage_from_session_jsonl,
)
from app.services.agent_repair_dispatcher import reap_stuck_auto_repair_tickets
from app.services.auto_repair_ticket_service import AutoRepairTicketService


def _engine(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'd.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_build_agent_events_think_tool_diff_recheck_and_mask():
    log = (
        "[claude-code:unrecognized_model] {\"model\":\"deepseek-v4-flash-vision-exp\"}\n"
        "页面有登录遮罩，准备点击关闭。{\"token\": \"secretTok999\"}\n"
        "TICKET_RESULT: SOLVED\n"
    )
    events = build_agent_events(
        log_text=log,
        diff_text="- old\n+ new selector\n",
        screenshot_rel="runtime/artifacts/art_abc/shot.png",
        recheck="PASS",
        status="SOLVED",
    )
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "think" in types
    assert "screenshot" in types
    assert "script_diff" in types
    assert "recheck" in types
    assert "status" in types
    think = next(e for e in events if e["type"] == "think")
    assert "secretTok999" not in think["text"]
    assert "登录遮罩" in think["text"]
    diff_ev = next(e for e in events if e["type"] == "script_diff")
    assert "new selector" in diff_ev["text"]


def test_build_agent_events_extracts_usage_from_cli_json():
    log = (
        '[claude-code:unrecognized_model] {"model":"deepseek-v4-flash"}\n'
        + json.dumps(
            {
                "type": "result",
                "result": "处理完成\nTICKET_RESULT: NEED_HUMAN\n",
                "usage": {"input_tokens": 1200, "output_tokens": 340, "cache_read_input_tokens": 80},
                "total_cost_usd": 0.0021,
                "duration_ms": 4100,
                "num_turns": 3,
                "model": "deepseek-v4-flash-vision-exp",
            }
        )
    )
    events = build_agent_events(log_text=log, status="NEED_HUMAN")
    usage_ev = next(e for e in events if e["type"] == "usage")
    assert "input 1200" in usage_ev["text"]
    assert "output 340" in usage_ev["text"]
    assert usage_ev["usage"]["total_tokens"] == 1540
    think = next(e for e in events if e["type"] == "think")
    assert "处理完成" in think["text"]
    assert "input_tokens" not in think["text"]


def test_collect_ticket_events_reads_artifacts(tmp_path: Path):
    runtime = tmp_path / "runtime"
    code = "art_ev1"
    (runtime / "logs" / "auto_repair").mkdir(parents=True)
    (runtime / "artifacts" / code).mkdir(parents=True)
    (runtime / "logs" / "auto_repair" / f"{code}.log").write_text("分析弹窗\nTICKET_RESULT: NEED_HUMAN\n", encoding="utf-8")
    (runtime / "artifacts" / code / "script.diff").write_text("--- a\n+++ b\n", encoding="utf-8")
    (runtime / "artifacts" / code / "shot.png").write_bytes(b"png")
    ticket = {
        "ticket_code": code,
        "status": "NEED_HUMAN",
        "diagnosis": "agent 报 SOLVED 但健康复检未通过 recheck=FAIL",
    }
    events = collect_ticket_events(runtime, ticket)
    types = [e["type"] for e in events]
    assert "think" in types
    assert "script_diff" in types
    assert "screenshot" in types
    assert "recheck" in types
    rec = next(e for e in events if e["type"] == "recheck")
    assert rec["text"] == "FAIL"


def test_reap_stuck_running_marks_failed(tmp_path: Path):
    engine = _engine(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = AutoRepairTicketService(engine=engine)
    ticket = svc.create_or_reuse(channel="PDD", shop_name="卫官", error_message="x")
    old = datetime(2026, 9, 1, 10, 0, 0)
    with Session(engine) as session:
        row = session.get(AutoRepairTicket, ticket["id"])
        row.status = "RUNNING"
        row.last_dispatched_at = old
        session.commit()
    art = runtime / "artifacts" / ticket["ticket_code"]
    art.mkdir(parents=True)
    (art / "agent.pid").write_text("4242", encoding="utf-8")

    with patch("app.services.agent_repair_dispatcher.AgentRepairDispatcher._kill_tree") as kill:
        result = reap_stuck_auto_repair_tickets(
            engine, runtime, now=datetime(2026, 9, 1, 12, 0, 0), running_timeout_seconds=600
        )
        kill.assert_called_once_with(4242)

    assert result["failed"] == 1
    fresh = svc.get_ticket(ticket["id"])
    assert fresh["status"] == "FAILED"


def test_reap_stuck_pending_retries_dispatch(tmp_path: Path):
    engine = _engine(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = AutoRepairTicketService(engine=engine)
    ticket = svc.create_or_reuse(channel="PDD", shop_name="卫官", error_message="x")
    with Session(engine) as session:
        row = session.get(AutoRepairTicket, ticket["id"])
        row.created_at = datetime(2026, 9, 1, 10, 0, 0)
        session.commit()

    with patch("app.services.agent_repair_dispatcher.trigger_auto_repair") as trig:
        trig.return_value = {"dispatched": True, "reason": "ok"}
        result = reap_stuck_auto_repair_tickets(
            engine, runtime, now=datetime(2026, 9, 1, 10, 20, 0), pending_age_seconds=300
        )
        assert result["retried"] == 1
        trig.assert_called_once()
        kwargs = trig.call_args.kwargs
        assert kwargs["channel"] == "PDD"
        assert kwargs["shop_name"] == "卫官"


def _assistant_line(input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "model": "deepseek-v4-flash-vision-exp",
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_write,
                },
            },
        }
    )


def test_extract_usage_from_session_jsonl_sums_assistant_turns(tmp_path: Path):
    path = tmp_path / "sess.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": {"content": "ticket art_59a0851252"}}),
                _assistant_line(10, 20, cache_read=100, cache_write=5),
                _assistant_line(3, 7, cache_read=50, cache_write=0),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    usage = extract_usage_from_session_jsonl(path)
    assert usage is not None
    assert usage["input_tokens"] == 13
    assert usage["output_tokens"] == 27
    assert usage["cache_read_tokens"] == 150
    assert usage["cache_write_tokens"] == 5
    assert usage["total_tokens"] == 40
    assert usage["num_turns"] == 2
    assert usage["model"] == "deepseek-v4-flash-vision-exp"
    assert usage["source"] == "session_jsonl"


def test_collect_ticket_usage_falls_back_to_matching_jsonl(tmp_path: Path):
    runtime = tmp_path / "runtime"
    code = "art_59a0851252"
    (runtime / "logs" / "auto_repair").mkdir(parents=True)
    (runtime / "artifacts" / code).mkdir(parents=True)
    (runtime / "logs" / "auto_repair" / f"{code}.log").write_text("纯文本报告\nTICKET_RESULT: SOLVED\n", encoding="utf-8")
    cache = runtime / "cache" / "claude_agent" / "projects" / "D--session-maintenance-system"
    cache.mkdir(parents=True)
    other = cache / "other.jsonl"
    other.write_text(
        json.dumps({"type": "user", "message": {"content": "ticket art_other"}})
        + "\n"
        + _assistant_line(999, 999)
        + "\n",
        encoding="utf-8",
    )
    hit = cache / "4a430593.jsonl"
    hit.write_text(
        json.dumps({"type": "user", "message": {"content": f"只处理本工单 {code}"}})
        + "\n"
        + _assistant_line(122, 636, cache_read=102528)
        + "\n",
        encoding="utf-8",
    )
    usage = collect_ticket_usage(runtime, code)
    assert usage is not None
    assert usage["input_tokens"] == 122
    assert usage["output_tokens"] == 636
    assert usage["cache_read_tokens"] == 102528
    assert usage["source"] == "session_jsonl"


def test_collect_ticket_usage_prefers_usage_json(tmp_path: Path):
    runtime = tmp_path / "runtime"
    code = "art_pref"
    art = runtime / "artifacts" / code
    art.mkdir(parents=True)
    (art / "usage.json").write_text(
        json.dumps({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3, "source": "cli_json"}),
        encoding="utf-8",
    )
    cache = runtime / "cache" / "claude_agent" / "projects" / "x"
    cache.mkdir(parents=True)
    (cache / "sess.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": code}}) + "\n" + _assistant_line(50, 50) + "\n",
        encoding="utf-8",
    )
    usage = collect_ticket_usage(runtime, code)
    assert usage["input_tokens"] == 1
    assert usage["source"] == "cli_json"

