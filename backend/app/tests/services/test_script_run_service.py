from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.script_run import ScriptRun
from app.services.script_run_service import ScriptRunService


def build_service(tmp_path: Path) -> ScriptRunService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runs.db'}")
    Base.metadata.create_all(engine)
    return ScriptRunService(engine=engine, runtime_root=tmp_path / "runtime")


def seed_run(service: ScriptRunService, *, status: str = "RUNNING", pid: int = 1234) -> str:
    artifact_dir = service.runtime_root / "artifacts" / "runs" / "run_test"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    control_file = artifact_dir / "control.json"
    control_file.write_text('{"pause": false, "cancel": false}', encoding="utf-8")

    with Session(service.engine) as session:
        row = ScriptRun(
            run_id="run_test",
            script_id=1,
            script_code="maintain_ks",
            directory_key="profile_001",
            run_mode="HEADLESS",
            timeout_seconds=600,
            status=status,
            pid=pid,
            artifact_dir=str(artifact_dir),
            control_file=str(control_file),
        )
        session.add(row)
        session.commit()
    return "run_test"


def test_pause_run_writes_control_and_updates_status(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    seed_run(service)

    result = service.pause_run("run_test")

    assert result["status"] == "PAUSED"
    control = (service.runtime_root / "artifacts" / "runs" / "run_test" / "control.json").read_text(encoding="utf-8")
    assert '"pause": true' in control


def test_resume_run_from_paused(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    seed_run(service, status="PAUSED")

    result = service.resume_run("run_test")

    assert result["status"] == "RUNNING"
    control = (service.runtime_root / "artifacts" / "runs" / "run_test" / "control.json").read_text(encoding="utf-8")
    assert '"pause": false' in control


def test_cancel_run_kills_process_and_marks_canceled(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    seed_run(service, pid=1234)

    with patch.object(service, "_kill_process_tree") as mock_kill:
        result = service.cancel_run("run_test")

    mock_kill.assert_called_once_with(1234)
    assert result["status"] == "CANCELED"
    control = (service.runtime_root / "artifacts" / "runs" / "run_test" / "control.json").read_text(encoding="utf-8")
    assert '"cancel": true' in control


def test_pause_non_running_run_rejected(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    seed_run(service, status="SUCCESS")

    with pytest.raises(AppError) as exc_info:
        service.pause_run("run_test")

    assert exc_info.value.error_code == "INVALID_STATUS"


def test_cancel_finished_run_rejected(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    seed_run(service, status="CANCELED")

    with pytest.raises(AppError) as exc_info:
        service.cancel_run("run_test")

    assert exc_info.value.error_code == "INVALID_STATUS"
