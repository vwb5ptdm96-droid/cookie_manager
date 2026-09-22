"""自动排障 dispatcher 纯逻辑单测（结果解析 / prompt 分支 / 命令构建）。

收尾线程与真实 claude 唤起属集成路径，留内部机冒烟验收（Spec AC-003/005/007）。
"""

import json
from pathlib import Path

import pytest

from app.services.agent_repair_dispatcher import (
    DEFAULT_MAX_SECONDS,
    DEFAULT_MAX_TURNS,
    DEEPSEEK_ANTHROPIC_BASE_URL,
    DEEPSEEK_FLASH_MODEL,
    DEEPSEEK_VISION_MODEL,
    AgentRepairDispatcher,
)


def _dispatcher() -> AgentRepairDispatcher:
    # 绕过 __init__（只测纯逻辑方法，不构造依赖）
    obj = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    obj.max_turns = 4
    obj._claude_path = None
    obj.project_root = Path(".")
    obj.logs_root = Path(".")
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


def test_parse_result_accepts_markdown_wrapped_ticket_result():
    d = _dispatcher()
    # 生产实绩：列表+加粗+反引号包住结论，原行首锚定会丢
    wrapped = (
        "报告如下：\n"
        "- **机器可读结论**：`TICKET_RESULT: NEED_HUMAN`\n"
        "等待系统收尾。\n"
    )
    assert d._parse_result(wrapped) == "NEED_HUMAN"
    assert d._parse_result("结论 TICKET_RESULT：FAILED") == "FAILED"
    # 仍拒绝裸 result:
    assert d._parse_result("工具输出 result: SOLVED 不算") is None
    # 多个时仍取最后一个
    mixed = "TICKET_RESULT: SOLVED\n- **结论**：`TICKET_RESULT: NEED_HUMAN`"
    assert d._parse_result(mixed) == "NEED_HUMAN"


def test_build_prompt_forbids_scanning_other_tickets():
    d = _dispatcher()
    prompt = d._build_prompt(_ticket(ticket_code="art_abc"), {"script_path": "x.py"})
    assert "art_abc" in prompt
    assert "禁止查询" in prompt or "禁止扫描" in prompt
    assert "其它工单" in prompt or "其他工单" in prompt


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


def test_build_command_skip_permissions_and_text_output():
    d = _dispatcher()
    cmd = d._build_command(r"C:\bin\claude.exe", "hello")
    assert cmd[0] == r"C:\bin\claude.exe"
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert "-p" in cmd
    assert "hello" in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "4"
    # cmd /c 会把 -p 之后的参数吞进 prompt，flags 必须在 -p 前面
    assert cmd.index("--output-format") < cmd.index("-p")
    assert cmd.index("--max-turns") < cmd.index("-p")
    assert cmd.index("--dangerously-skip-permissions") < cmd.index("-p")


def test_build_command_cmd_wrapper_keeps_skip_permissions():
    d = _dispatcher()
    cmd = d._build_command(r"C:\npm\claude.cmd", "prompt")
    assert cmd[:3] == ["cmd", "/c", r"C:\npm\claude.cmd"]
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd.index("--output-format") < cmd.index("-p")


def test_child_env_strips_proxy_and_injects_deepseek(tmp_path):
    d = _dispatcher()
    base = {
        "PATH": "/usr/bin",
        "HTTP_PROXY": "http://127.0.0.1:7897",
        "HTTPS_PROXY": "http://127.0.0.1:7897",
        "ALL_PROXY": "http://127.0.0.1:7897",
        "http_proxy": "http://127.0.0.1:7897",
        "https_proxy": "http://127.0.0.1:7897",
        "all_proxy": "http://127.0.0.1:7897",
        "UNRELATED": "keep-me",
    }
    env = d._build_child_env(base, auth_token="sk-test-token", config_dir=tmp_path)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert key not in env
    assert env["UNRELATED"] == "keep-me"
    assert env["PATH"] == "/usr/bin"
    assert env["ANTHROPIC_BASE_URL"] == DEEPSEEK_ANTHROPIC_BASE_URL
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test-token"
    assert env["ANTHROPIC_MODEL"] == DEEPSEEK_VISION_MODEL
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == DEEPSEEK_VISION_MODEL
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == DEEPSEEK_VISION_MODEL
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == DEEPSEEK_FLASH_MODEL
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == DEEPSEEK_VISION_MODEL
    assert env["CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT"] == "1"
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert "api.deepseek.com" in env["NO_PROXY"]
    assert "no_proxy" not in env


def test_resolve_auth_token_prefers_deepseek_api_key(tmp_path):
    d = _dispatcher()
    token = d._resolve_auth_token(
        {
            "DEEPSEEK_API_KEY": "from-deepseek",
            "ANTHROPIC_AUTH_TOKEN": "from-anthropic",
            "USERPROFILE": str(tmp_path),
            "HOME": str(tmp_path),
        }
    )
    assert token == "from-deepseek"


def test_resolve_auth_token_reads_claude_settings(tmp_path):
    d = _dispatcher()
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "from-settings", "HTTP_PROXY": "http://127.0.0.1:7897"}}),
        encoding="utf-8",
    )
    token = d._resolve_auth_token({"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)})
    assert token == "from-settings"


def test_isolated_config_has_model_and_no_proxy(tmp_path):
    d = _dispatcher()
    config_dir = d._ensure_isolated_config(tmp_path / "claude_agent")
    data = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
    env = data.get("env") or {}
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert data.get("model") == DEEPSEEK_VISION_MODEL


def test_default_budget_is_wide_enough_for_real_repair():
    assert DEFAULT_MAX_TURNS >= 20
    assert DEFAULT_MAX_SECONDS >= 600
    d = AgentRepairDispatcher(ticket_service=object(), project_root=Path("."), logs_root=Path("."))
    assert d.max_turns == DEFAULT_MAX_TURNS
    assert d.max_seconds == DEFAULT_MAX_SECONDS


def test_budget_from_environ_overrides_and_rejects_invalid():
    d = _dispatcher()
    assert d._budget_from_environ({"AUTO_REPAIR_MAX_TURNS": "40", "AUTO_REPAIR_MAX_SECONDS": "1800"}) == (40, 1800)
    assert d._budget_from_environ({"AUTO_REPAIR_MAX_TURNS": "nope"}) == (DEFAULT_MAX_TURNS, DEFAULT_MAX_SECONDS)


def test_resolve_claude_prefers_cmd(monkeypatch):
    d = _dispatcher()

    def fake_which(name: str):
        mapping = {"claude.cmd": r"C:\npm\claude.cmd", "claude": r"C:\npm\claude.ps1"}
        return mapping.get(name)

    monkeypatch.setattr("app.services.agent_repair_dispatcher.shutil.which", fake_which)
    assert d._resolve_claude() == r"C:\npm\claude.cmd"


def test_fake_solved_without_recheck_pass_is_need_human():
    d = _dispatcher()
    d._recheck_health = lambda code: "FAIL"  # type: ignore[method-assign]
    status, reason = d._finalize_agent_result(_ticket(health_task_code="ht_1"), "SOLVED")
    assert status == "NEED_HUMAN"
    assert reason and "recheck" in reason.lower()


def test_solved_only_when_recheck_pass():
    d = _dispatcher()
    d._recheck_health = lambda code: "PASS"  # type: ignore[method-assign]
    status, reason = d._finalize_agent_result(_ticket(health_task_code="ht_1"), "SOLVED")
    assert status == "SOLVED"
    assert reason and "PASS" in reason


def test_exception_solved_also_requires_recheck_pass():
    d = _dispatcher()
    d._recheck_health = lambda code: "PASS"  # type: ignore[method-assign]
    status, _ = d._finalize_agent_result(
        _ticket(issue_type="EXCEPTION", health_task_code="ht_1"), "SOLVED"
    )
    assert status == "SOLVED"
    d._recheck_health = lambda code: "FAIL"  # type: ignore[method-assign]
    status, _ = d._finalize_agent_result(
        _ticket(issue_type="EXCEPTION", health_task_code="ht_1"), "SOLVED"
    )
    assert status == "NEED_HUMAN"


def test_risk_never_solved_even_if_recheck_pass():
    d = _dispatcher()
    d._recheck_health = lambda code: "PASS"  # type: ignore[method-assign]
    status, reason = d._finalize_agent_result(
        _ticket(issue_type="RISK", health_task_code="ht_1"), "SOLVED"
    )
    assert status == "NEED_HUMAN"
    assert reason and "RISK" in reason


def test_need_human_skips_recheck():
    d = _dispatcher()
    called = []

    def boom(code):
        called.append(code)
        raise AssertionError("RISK/NEED_HUMAN 不应复检")

    d._recheck_health = boom  # type: ignore[method-assign]
    status, _ = d._finalize_agent_result(_ticket(health_task_code="ht_1"), "NEED_HUMAN")
    assert status == "NEED_HUMAN"
    assert called == []


def test_solved_without_health_task_is_need_human():
    d = _dispatcher()
    d._recheck_health = lambda code: "SKIPPED"  # type: ignore[method-assign]
    status, reason = d._finalize_agent_result(_ticket(), "SOLVED")
    assert status == "NEED_HUMAN"
    assert reason and "recheck" in reason.lower()


def test_build_prompt_loads_sop_memory_and_instance_pack(tmp_path):
    d = _dispatcher()
    d.project_root = tmp_path
    agent_dir = tmp_path / "docs" / "agent"
    (agent_dir / "memory" / "shops").mkdir(parents=True)
    (agent_dir / "memory" / "scripts").mkdir(parents=True)
    (agent_dir / "SOP-操作手册.md").write_text("# SOP\n强制红线XYZ\n", encoding="utf-8")
    (agent_dir / "memory" / "项目运转.md").write_text("运转记忆ABC\n", encoding="utf-8")
    (agent_dir / "memory" / "shops" / "卫官.md").write_text("店铺笔记SHOPMEM\n", encoding="utf-8")
    prompt = d._build_prompt(
        _ticket(health_task_code="ht_pdd"),
        {
            "script_path": r"runtime\scripts\pdd.py",
            "profile_path": r"runtime\profiles\pdd-weiguang",
            "log_tail": "timeout at selector .login",
        },
    )
    assert "强制红线XYZ" in prompt
    assert "运转记忆ABC" in prompt
    assert "店铺笔记SHOPMEM" in prompt
    assert "ht_pdd" in prompt
    assert "9333" in prompt
    assert "runtime\\scripts\\pdd.py" in prompt or "runtime/scripts/pdd.py" in prompt
    assert "tools/cdp_inspector.py" in prompt
    assert ".claude/tools" not in prompt
    assert "art_abc" in prompt
    assert "平台会强制" in prompt or "复检" in prompt


def test_build_prompt_cdp_screenshot_goes_to_artifacts():
    d = _dispatcher()
    d.project_root = Path(".")
    prompt = d._build_prompt(_ticket(), {"script_path": "x.py"})
    assert "tools/cdp_inspector.py" in prompt
    assert "runtime/artifacts" in prompt or "runtime\\artifacts" in prompt
    assert ".claude/tools/cdp_inspector.py" not in prompt


def test_prepare_script_backup_raises_when_file_missing(tmp_path):
    d = _dispatcher()
    d.project_root = tmp_path
    d.logs_root = tmp_path / "logs"
    (tmp_path / "runtime" / "scripts").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        d._prepare_script_backup(
            _ticket(issue_type="FAIL"),
            {"script_path": str(tmp_path / "runtime" / "scripts" / "gone.py")},
        )


def test_cdp_inspector_script_exists():
    root = Path(__file__).resolve().parents[4]
    path = root / "tools" / "cdp_inspector.py"
    assert path.is_file()
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_reap_always_closes_debug_browser_in_finally():
    import inspect

    src = inspect.getsource(AgentRepairDispatcher._reap)
    finally_src = src.split("finally:", 1)[1]
    assert "_shutdown_browser" in finally_src


