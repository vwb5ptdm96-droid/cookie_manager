"""自动排障 dispatcher 纯逻辑单测（结果解析 / prompt 分支 / 命令构建）。

收尾线程与真实 claude 唤起属集成路径，留内部机冒烟验收（Spec AC-003/005/007）。
"""

from pathlib import Path

from app.services.agent_repair_dispatcher import AgentRepairDispatcher


def _dispatcher() -> AgentRepairDispatcher:
    # 绕过 __init__（只测纯逻辑方法，不构造依赖）
    obj = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    obj.max_turns = 4
    return obj


def _ticket(**overrides):
    t = dict(id=1, ticket_code="art_abc", channel="PDD", shop_name="卫官",
             cdp_port=9333, issue_type="FAIL", status="PENDING",
             error_message="token 泄露样例 secretTok123", diagnosis=None)
    t.update(overrides)
    return t


def test_parse_result_only_line_anchored_ticket_result():
    d = _dispatcher()
    # 正文裸 result: 字样不命中（防 tool 输出/tool 正文误判）
    assert d._parse_result("正文提到 result: SOLVED 但非结论行") is None
    # 行首 TICKET_RESULT 命中
    assert d._parse_result("阻挡原因：浮层\nTICKET_RESULT: SOLVED") == "SOLVED"
    # 大小写/缩进/全角冒号容忍
    assert d._parse_result("  ticket_result：need_human") == "NEED_HUMAN"
    # 多个标记取最后一个
    text = "TICKET_RESULT: SOLVED\n再次说明\nTICKET_RESULT: NEED_HUMAN"
    assert d._parse_result(text) == "NEED_HUMAN"


def test_build_prompt_risk_only_diagnose():
    d = _dispatcher()
    prompt = d._build_prompt(_ticket(issue_type="RISK"), {"script_path": "x.py"})
    assert "只诊断判级" in prompt
    assert "严禁" in prompt
    # RISK 不允许消除弹窗/重跑脚本
    assert "--skip-db" not in prompt
    assert "NEED_HUMAN" in prompt


def test_build_prompt_normal_allows_rerun():
    d = _dispatcher()
    prompt = d._build_prompt(_ticket(issue_type="FAIL"), {"script_path": "x.py"})
    assert "--skip-db" in prompt
    assert "SOLVED" in prompt


def test_build_command_handles_cmd_wrapper():
    d = _dispatcher()
    cmd = d._build_command("C:\\npm\\claude.cmd", "prompt")
    assert cmd[0] == "cmd" and cmd[1] == "/c" and cmd[2] == "C:\\npm\\claude.cmd"
    cmd_exe = d._build_command("C:\\bin\\claude.exe", "prompt")
    assert cmd_exe[0] == "C:\\bin\\claude.exe"


def test_prompt_masks_error_message():
    d = _dispatcher()
    prompt = d._build_prompt(_ticket(error_message='响应异常 {"token": "secretTok123"}'), {})
    assert "secretTok123" not in prompt
