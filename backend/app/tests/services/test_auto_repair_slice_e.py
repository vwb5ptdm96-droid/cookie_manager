"""Slice E：选项 B 三分支契约（FAIL / EXCEPTION / RISK）。"""

from pathlib import Path

from app.services.agent_repair_dispatcher import AgentRepairDispatcher, DEFAULT_MAX_SECONDS, DEFAULT_MAX_TURNS


def _dispatcher() -> AgentRepairDispatcher:
    obj = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    obj.max_turns = 4
    obj._claude_path = None
    obj.project_root = Path(".")
    obj.logs_root = Path(".")
    return obj


def _ticket(issue_type: str, **overrides):
    t = dict(
        id=1,
        ticket_code="art_e",
        channel="PDD",
        shop_name="卫官",
        cdp_port=9333,
        issue_type=issue_type,
        status="PENDING",
        error_message="fail",
        health_task_code="ht_1",
        diagnosis=None,
    )
    t.update(overrides)
    return t


def test_fail_and_exception_allow_script_repair_and_solved_only_on_recheck_pass():
    d = _dispatcher()
    for issue in ("FAIL", "EXCEPTION"):
        prompt = d._build_prompt(_ticket(issue), {"script_path": "runtime/scripts/x.py"})
        assert "--skip-db" in prompt
        assert "tools/cdp_inspector.py" in prompt
        assert "只诊断判级" not in prompt

        d._recheck_health = lambda code: "PASS"
        status, _ = d._finalize_agent_result(_ticket(issue), "SOLVED")
        assert status == "SOLVED"

        d._recheck_health = lambda code: "FAIL"
        status, reason = d._finalize_agent_result(_ticket(issue), "SOLVED")
        assert status == "NEED_HUMAN"
        assert reason and "recheck" in reason.lower()


def test_risk_diagnose_only_never_solved_never_backup(tmp_path: Path):
    d = _dispatcher()
    d.project_root = tmp_path
    d.logs_root = tmp_path / "runtime" / "logs"
    prompt = d._build_prompt(_ticket("RISK"), {"script_path": "runtime/scripts/x.py"})
    assert "只诊断判级" in prompt
    assert "--skip-db" not in prompt
    assert "禁止输出 SOLVED" in prompt

    d._recheck_health = lambda code: "PASS"
    status, reason = d._finalize_agent_result(_ticket("RISK"), "SOLVED")
    assert status == "NEED_HUMAN"
    assert reason and "RISK" in reason

    scripts = tmp_path / "runtime" / "scripts"
    scripts.mkdir(parents=True)
    src = scripts / "x.py"
    src.write_text("ORIG\n", encoding="utf-8")
    run_ctx = {"script_path": str(src)}
    d._prepare_script_backup(_ticket("RISK"), run_ctx)
    assert run_ctx.get("_backup_path") is None
    assert AgentRepairDispatcher._should_rollback("RISK", "NEED_HUMAN", False) is False


def test_cli_budget_and_skip_permissions_still_on_all_branches():
    d = _dispatcher()
    cmd = d._build_command(r"C:\npm\claude.cmd", "p")
    assert "--dangerously-skip-permissions" in cmd
    assert DEFAULT_MAX_TURNS >= 20
    assert DEFAULT_MAX_SECONDS >= 600
