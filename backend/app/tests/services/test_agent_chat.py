from pathlib import Path

from sqlalchemy import create_engine

from app.core.database import Base
from app.services.agent_chat_service import (
    AgentChatService,
    append_chat,
    build_chat_prompt,
    load_chat_history,
)


def test_build_chat_prompt_includes_ticket_and_forbids_writes() -> None:
    prompt = build_chat_prompt(
        "为什么失败？",
        ticket={
            "ticket_code": "art_abc",
            "status": "FAILED",
            "issue_type": "FAIL",
            "channel": "PDD",
            "shop_name": "卫官",
            "health_task_code": "ht_1",
            "cdp_port": 9237,
            "error_message": "timeout",
            "diagnosis": "弹窗",
        },
        history=[{"role": "user", "text": "还在吗"}, {"role": "assistant", "text": "在"}],
    )
    assert "不要改文件" in prompt
    assert "TICKET_RESULT" in prompt
    assert "art_abc" in prompt
    assert "9237" in prompt
    assert "为什么失败？" in prompt
    assert "还在吗" in prompt


def test_chat_history_roundtrip(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    append_chat(runtime, "art_abc", "user", "hi")
    append_chat(runtime, "art_abc", "assistant", "hello")
    items = load_chat_history(runtime, "art_abc")
    assert [i["role"] for i in items] == ["user", "assistant"]
    assert items[0]["text"] == "hi"


def test_ask_empty_rejected(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    svc = AgentChatService(engine, tmp_path / "runtime", tmp_path)
    import pytest
    from app.core.errors import AppError

    with pytest.raises(AppError) as exc:
        svc.ask("   ")
    assert exc.value.error_code == "AGENT_CHAT_EMPTY"


def test_ask_without_ticket_uses_watcher_loop(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    svc = AgentChatService(engine, tmp_path / "runtime", tmp_path)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def fake_loop(**kwargs):
        execute = kwargs["execute"]
        denied = execute("script_edit", {"content": "bad"})
        assert denied["ok"] is False
        return {"text": "今日健康 FAIL 0", "turns": 1, "stop": "end_turn"}

    monkeypatch.setattr("app.services.agent_loop.run_tool_loop", fake_loop)
    out = svc.ask("今天怎么样")
    assert "FAIL" in out["reply"]
    assert out["ticket_id"] is None
