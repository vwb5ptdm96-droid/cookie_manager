"""Slice C：Profile 持锁 + 脚本备份/diff/复检失败回滚。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.errors import AppError
from app.services.agent_repair_dispatcher import AgentRepairDispatcher
from app.services.profile_service import ProfilePayload, ProfileService


def _dispatcher(tmp_path: Path) -> AgentRepairDispatcher:
    obj = AgentRepairDispatcher.__new__(AgentRepairDispatcher)
    obj.project_root = tmp_path
    obj.logs_root = tmp_path / "runtime" / "logs"
    obj.max_turns = 4
    return obj


def _profile_service(tmp_path: Path) -> ProfileService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profiles.db'}")
    Base.metadata.create_all(engine)
    return ProfileService(engine=engine, runtime_root=tmp_path / "runtime")


def test_should_rollback_matrix() -> None:
    rb = AgentRepairDispatcher._should_rollback
    assert rb("FAIL", "NEED_HUMAN", False) is True
    assert rb("EXCEPTION", "FAILED", False) is True
    assert rb("FAIL", "SOLVED", False) is False
    assert rb("RISK", "NEED_HUMAN", False) is False
    assert rb("FAIL", "NEED_HUMAN", True) is False


def test_acquire_for_auto_repair_locks_unlocked_profile(tmp_path: Path) -> None:
    service = _profile_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="p1", relative_path="profiles/ks/demo"))
    result = service.acquire_for_auto_repair("p1", owner="auto-repair:art_abc")
    assert result["is_locked"] is True
    assert result["lock_owner"] == "auto-repair:art_abc"


def test_acquire_for_auto_repair_steals_matching_run_lock(tmp_path: Path) -> None:
    service = _profile_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="p1", relative_path="profiles/ks/demo"))
    service.lock("p1", owner="run:run_deadbeef")
    result = service.acquire_for_auto_repair("p1", owner="auto-repair:art_abc", steal_run_id="run_deadbeef")
    assert result["lock_owner"] == "auto-repair:art_abc"
    assert result["is_locked"] is True


def test_acquire_for_auto_repair_rejects_foreign_lock(tmp_path: Path) -> None:
    service = _profile_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="p1", relative_path="profiles/ks/demo"))
    service.lock("p1", owner="run:other")
    with pytest.raises(AppError) as exc_info:
        service.acquire_for_auto_repair("p1", owner="auto-repair:art_abc", steal_run_id="run_deadbeef")
    assert exc_info.value.error_code == "PROFILE_LOCKED"


def test_unlock_if_owner_only_releases_matching_owner(tmp_path: Path) -> None:
    service = _profile_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="p1", relative_path="profiles/ks/demo"))
    service.lock("p1", owner="auto-repair:art_abc")
    still = service.unlock_if_owner("p1", "auto-repair:other")
    assert still["is_locked"] is True
    assert still["lock_owner"] == "auto-repair:art_abc"
    released = service.unlock_if_owner("p1", "auto-repair:art_abc")
    assert released["is_locked"] is False
    assert released["lock_owner"] is None


def test_snapshot_diff_and_rollback_restores_script(tmp_path: Path) -> None:
    d = _dispatcher(tmp_path)
    scripts = tmp_path / "runtime" / "scripts"
    scripts.mkdir(parents=True)
    src = scripts / "pdd.py"
    src.write_text("ORIG\n", encoding="utf-8")
    ticket = {"ticket_code": "art_abc", "issue_type": "FAIL"}
    run_ctx = {"script_path": str(src)}
    d._prepare_script_backup(ticket, run_ctx)
    assert Path(run_ctx["_backup_path"]).is_file()
    src.write_text("NEW\n", encoding="utf-8")
    d._apply_script_governance(ticket, run_ctx, "NEED_HUMAN")
    assert src.read_text(encoding="utf-8") == "ORIG\n"
    diff_path = tmp_path / "runtime" / "artifacts" / "art_abc" / "script.diff"
    assert diff_path.is_file()
    diff_text = diff_path.read_text(encoding="utf-8")
    assert "ORIG" in diff_text and "NEW" in diff_text


def test_governance_keeps_script_on_solved(tmp_path: Path) -> None:
    d = _dispatcher(tmp_path)
    scripts = tmp_path / "runtime" / "scripts"
    scripts.mkdir(parents=True)
    src = scripts / "pdd.py"
    src.write_text("ORIG\n", encoding="utf-8")
    ticket = {"ticket_code": "art_abc", "issue_type": "FAIL"}
    run_ctx = {"script_path": str(src)}
    d._prepare_script_backup(ticket, run_ctx)
    src.write_text("NEW\n", encoding="utf-8")
    d._apply_script_governance(ticket, run_ctx, "SOLVED")
    assert src.read_text(encoding="utf-8") == "NEW\n"
    assert (tmp_path / "runtime" / "artifacts" / "art_abc" / "script.diff").is_file()


def test_risk_skips_backup_and_rollback(tmp_path: Path) -> None:
    d = _dispatcher(tmp_path)
    scripts = tmp_path / "runtime" / "scripts"
    scripts.mkdir(parents=True)
    src = scripts / "pdd.py"
    src.write_text("ORIG\n", encoding="utf-8")
    ticket = {"ticket_code": "art_abc", "issue_type": "RISK"}
    run_ctx = {"script_path": str(src)}
    d._prepare_script_backup(ticket, run_ctx)
    assert "_backup_path" not in run_ctx
    src.write_text("NEW\n", encoding="utf-8")
    d._apply_script_governance(ticket, run_ctx, "NEED_HUMAN")
    assert src.read_text(encoding="utf-8") == "NEW\n"
