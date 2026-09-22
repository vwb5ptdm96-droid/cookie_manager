import json

from app.services.agent_event_builder import unwrap_cli_log
from app.services.agent_repair_dispatcher import AgentRepairDispatcher


def test_unwrap_cli_json_envelope_exposes_ticket_result():
    payload = {
        "type": "result",
        "result": "诊断完成\nTICKET_RESULT: SOLVED\nrecheck=PASS",
        "usage": {"input_tokens": 11, "output_tokens": 7},
        "model": "deepseek-v4-flash-vision-exp",
    }
    log = "[claude-code:unrecognized_model] skip\n" + json.dumps(payload, ensure_ascii=False)
    body, usage = unwrap_cli_log(log)
    assert "TICKET_RESULT: SOLVED" in body
    assert usage is not None
    assert usage["input_tokens"] == 11
    d = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    assert d._parse_result(body) == "SOLVED"


def test_unwrap_stream_json_uses_last_result_object():
    lines = [
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "先看页面"}]}},
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "type": "result",
                "result": "结论 TICKET_RESULT: NEED_HUMAN",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
            ensure_ascii=False,
        ),
    ]
    body, usage = unwrap_cli_log("\n".join(lines))
    assert "NEED_HUMAN" in body
    assert usage is not None
    d = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    assert d._parse_result(body) == "NEED_HUMAN"


def test_unwrap_nested_result_content_blocks():
    payload = {
        "type": "result",
        "result": {
            "content": [
                {"type": "text", "text": "阻挡是滑块\nTICKET_RESULT: NEED_HUMAN\n"},
            ]
        },
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    body, _usage = unwrap_cli_log(json.dumps(payload, ensure_ascii=False))
    d = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    assert d._parse_result(body) == "NEED_HUMAN"


def test_unwrap_plain_text_unchanged():
    text = "分析弹窗\nTICKET_RESULT: FAILED\n"
    body, usage = unwrap_cli_log(text)
    assert body == text
    assert usage is None
