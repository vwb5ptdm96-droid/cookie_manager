from app.services.agent_loop import run_tool_loop
from app.services.agent_tools import ToolRuntime, validate_ticket_conclude, tool_specs


def test_validate_ticket_conclude_requires_recheck_pass():
    denied = validate_ticket_conclude(requested="SOLVED", issue_type="FAIL", last_recheck=None)
    assert denied["ok"] is False
    ok = validate_ticket_conclude(requested="SOLVED", issue_type="FAIL", last_recheck="PASS")
    assert ok["ok"] is True
    assert ok["stop_loop"] is True
    risk = validate_ticket_conclude(requested="SOLVED", issue_type="RISK", last_recheck="PASS")
    assert risk["ok"] is False


def test_watcher_cannot_edit_script(tmp_path):
    from sqlalchemy import create_engine

    from app.core.database import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    runtime = ToolRuntime(
        engine=engine,
        runtime_root=tmp_path,
        project_root=tmp_path,
        role="watcher",
        ticket={"ticket_code": "art_1", "issue_type": "FAIL"},
    )
    out = runtime.execute("script_edit", {"content": "print(1)"})
    assert out["ok"] is False
    assert "不能使用" in out["error"]


def test_risk_repairer_cannot_edit_script(tmp_path):
    from sqlalchemy import create_engine

    from app.core.database import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    runtime = ToolRuntime(
        engine=engine,
        runtime_root=tmp_path,
        project_root=tmp_path,
        role="repairer",
        ticket={"ticket_code": "art_1", "issue_type": "RISK"},
    )
    out = runtime.execute("script_edit", {"content": "x"})
    assert out["ok"] is False


def test_loop_runs_tool_then_text_reply():
    calls = []

    def complete(*, system, messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "tool_use", "id": "1", "name": "site_ops_summary", "input": {}},
                ],
            }
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "健康 FAIL 1 家"}]}

    def execute(name, args):
        assert name == "site_ops_summary"
        return {"ok": True, "data": {"health": {"fail": 1}}}

    result = run_tool_loop(
        system="sys",
        user="今天怎么样",
        tools=tool_specs("watcher"),
        execute=execute,
        complete=complete,
        max_turns=4,
    )
    assert result["stop"] == "end_turn"
    assert "FAIL" in result["text"]
    assert result["turns"] == 2


def test_cookie_conclude_rules():
    denied = validate_ticket_conclude(
        requested="SOLVED", issue_type="JOB_TIMEOUT", last_recheck=None, kind="cookie_sync"
    )
    assert denied["ok"] is False
    mapping = validate_ticket_conclude(
        requested="SOLVED", issue_type="NO_MAPPING", last_recheck="PASS", kind="cookie_sync"
    )
    assert mapping["ok"] is False
    ok = validate_ticket_conclude(
        requested="NEED_HUMAN", issue_type="NO_MAPPING", last_recheck=None, kind="cookie_sync"
    )
    assert ok["ok"] is True


def test_collector_cannot_use_cdp(tmp_path):
    from sqlalchemy import create_engine

    from app.core.database import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    runtime = ToolRuntime(
        engine=engine,
        runtime_root=tmp_path,
        project_root=tmp_path,
        role="collector",
        ticket={"ticket_code": "cst_1", "kind": "cookie_sync", "issue_type": "NO_MAPPING"},
    )
    out = runtime.execute("cdp_inspect", {})
    assert out["ok"] is False
    assert "不能使用" in out["error"]


def test_loop_stops_on_ticket_conclude():
    def complete(*, system, messages, tools):
        return {
            "stop_reason": "tool_use",
            "content": [
                {"type": "tool_use", "id": "c1", "name": "ticket_conclude", "input": {"status": "NEED_HUMAN"}},
            ],
        }

    def execute(name, args):
        return validate_ticket_conclude(requested=args["status"], issue_type="FAIL", last_recheck=None)

    result = run_tool_loop(
        system="sys",
        user="关单",
        tools=tool_specs("repairer"),
        execute=execute,
        complete=complete,
        max_turns=3,
    )
    assert result["stop"] == "concluded"
    assert result["conclusion"]["status"] == "NEED_HUMAN"


def test_loop_serializes_datetime_tool_output():
    from datetime import datetime

    calls = []

    def complete(*, system, messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": "1", "name": "site_env_last_check", "input": {}}],
            }
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "环境正常"}]}

    def execute(name, args):
        return {"ok": True, "data": {"items": [{"created_at": datetime(2026, 9, 22, 17, 0, 0)}]}}

    result = run_tool_loop(
        system="sys",
        user="环境",
        tools=tool_specs("watcher"),
        execute=execute,
        complete=complete,
        max_turns=4,
    )
    assert result["stop"] == "end_turn"
    dumped = calls[1][2]["content"][0]["content"]
    assert "2026-09-22" in dumped
