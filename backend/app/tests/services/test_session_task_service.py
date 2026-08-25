from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.repair_ticket import ManualRepairTicket
from app.models.session_task import SessionMaintenanceTask
from app.services.profile_service import ProfilePayload, ProfileService
from app.services.script_service import ScriptService
from app.services.session_task_service import SessionTaskPayload, SessionTaskService


SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
result = {
    "status": os.environ.get("EXPECTED_STATUS", "SUCCESS"),
    "message": os.environ.get("EXPECTED_MESSAGE", "task finished"),
}
artifact_dir.joinpath("result.json").write_text(json.dumps(result), encoding="utf-8")
print("runner:", result["status"])
"""


def bootstrap_dependencies(tmp_path: Path) -> tuple[object, Path]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'tasks.db'}")
    Base.metadata.create_all(engine)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True)
    profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
    script_service = ScriptService(engine=engine, runtime_root=runtime_root)

    profile_service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            task_id=None,
            relative_path="profiles/ks/demo-user",
        )
    )

    script_service.upload(
        script_name="快手维护脚本",
        script_code="maintain_ks",
        script_type="MAINTAIN",
        platform="KUAISHOU",
        version="1.0.0",
        description=None,
        filename="main.py",
        content=SCRIPT_SOURCE,
    )

    return engine, runtime_root


def test_session_task_service_create_and_execute_success(tmp_path: Path) -> None:
    engine, runtime_root = bootstrap_dependencies(tmp_path)
    service = SessionTaskService(engine=engine, runtime_root=runtime_root)

    created = service.create_task(
        SessionTaskPayload(
            task_name="快手店铺会话维护",
            channel="KUAISHOU",
            mobile_phone="13800000001",
            account_alias="demo-shop",
            related_dns=["s.kwaixiaodian.com"],
            script_code="maintain_ks",
            profile_key="profile_001",
            schedule_type="MANUAL",
            schedule_value="manual",
            script_config={"expected_status": "SUCCESS", "message": "refresh ok"},
        )
    )
    result = service.execute_task(created["task_code"])

    artifact_dir = Path(result["artifact_dir"])

    assert created["status"] == "INIT"
    assert result["status"] == "VALID"
    assert artifact_dir.exists()
    assert artifact_dir.joinpath("config.json").exists()
    assert artifact_dir.joinpath("result.json").exists()
    assert result["last_run_status"] == "SUCCESS"


def test_session_task_service_rejects_locked_profile(tmp_path: Path) -> None:
    engine, runtime_root = bootstrap_dependencies(tmp_path)
    profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
    profile_service.lock("profile_001", owner="task-other")

    service = SessionTaskService(engine=engine, runtime_root=runtime_root)
    created = service.create_task(
        SessionTaskPayload(
            task_name="快手店铺会话维护",
            channel="KUAISHOU",
            mobile_phone="13800000001",
            account_alias="demo-shop",
            related_dns=["s.kwaixiaodian.com"],
            script_code="maintain_ks",
            profile_key="profile_001",
            schedule_type="MANUAL",
            schedule_value="manual",
            script_config={"expected_status": "SUCCESS"},
        )
    )

    with pytest.raises(AppError) as exc_info:
        service.execute_task(created["task_code"])

    assert exc_info.value.error_code == "PROFILE_LOCKED"


def test_session_task_service_marks_risk_and_creates_repair_ticket(tmp_path: Path) -> None:
    engine, runtime_root = bootstrap_dependencies(tmp_path)
    service = SessionTaskService(engine=engine, runtime_root=runtime_root)

    created = service.create_task(
        SessionTaskPayload(
            task_name="快手店铺会话维护",
            channel="KUAISHOU",
            mobile_phone="13800000001",
            account_alias="demo-shop",
            related_dns=["s.kwaixiaodian.com"],
            script_code="maintain_ks",
            profile_key="profile_001",
            schedule_type="MANUAL",
            schedule_value="manual",
            script_config={"expected_status": "RISK", "message": "need qr login"},
        )
    )
    result = service.execute_task(created["task_code"])

    with Session(engine) as session:
        ticket = session.execute(select(ManualRepairTicket)).scalar_one()
        task = session.execute(select(SessionMaintenanceTask)).scalar_one()

    assert result["status"] == "RISK"
    assert ticket.task_code == created["task_code"]
    assert ticket.status == "OPEN"
    assert task.status == "RISK"
