import json
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.profile_registry import ProfileRegistry
from app.models.repair_ticket import ManualRepairTicket
from app.models.session_task import SessionMaintenanceTask
from app.services.health_check_service import HealthCheckPayload, HealthCheckService
from app.services.profile_service import ProfilePayload, ProfileService
from app.services.repair_service import RepairService
from app.services.script_service import ScriptService
from app.services.session_task_service import SessionTaskPayload, SessionTaskService


MAINTAIN_SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
result = {"status": os.environ.get("EXPECTED_STATUS", "SUCCESS"), "message": "risk happened"}
artifact_dir.joinpath("result.json").write_text(json.dumps(result), encoding="utf-8")
"""

MANUAL_SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
artifact_dir.joinpath("result.json").write_text(json.dumps({"status": "SUCCESS", "message": "browser opened"}), encoding="utf-8")
"""


def bootstrap_risk_context(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'repairs.db'}")
    Base.metadata.create_all(engine)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table ods_cookie_playwright (
                    channel varchar(32) not null,
                    shop_name varchar(64) not null,
                    mobile_phone varchar(32) not null,
                    DNS varchar(64) not null,
                    str_cookie text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into ods_cookie_playwright (
                    channel, shop_name, mobile_phone, DNS, str_cookie
                ) values (
                    :channel, :shop_name, :mobile_phone, :dns, :str_cookie
                )
                """
            ),
            {
                "channel": "KUAISHOU",
                "shop_name": "demo-shop",
                "mobile_phone": "13800000001",
                "dns": "s.kwaixiaodian.com",
                "str_cookie": "sid=1",
            },
        )

    profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
    script_service = ScriptService(engine=engine, runtime_root=runtime_root)
    task_service = SessionTaskService(engine=engine, runtime_root=runtime_root)

    profile_service.upsert(
        ProfilePayload(
            profile_key="profile_001",
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
        content=MAINTAIN_SCRIPT_SOURCE,
    )
    script_service.upload(
        script_name="快手人工修复脚本",
        script_code="manual_ks",
        script_type="MANUAL",
        platform="KUAISHOU",
        version="1.0.0",
        description=None,
        filename="repair.py",
        content=MANUAL_SCRIPT_SOURCE,
    )

    task = task_service.create_task(
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
            script_config={"expected_status": "RISK"},
        )
    )
    task_service.execute_task(task["task_code"])

    health_service = HealthCheckService(
        engine=engine,
        runtime_root=runtime_root,
        request_runner=lambda **_: {"status_code": 200, "body": {"status": "ok"}},
    )
    health_service.create_check(
        HealthCheckPayload(
            check_name="店铺主页登录态检测",
            cookie_table="ods_cookie_playwright",
            channel="KUAISHOU",
            shop_name="demo-shop",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
            method="GET",
            check_url="http://example.test/health",
            success_rule={"equals": {"path": "status", "value": "ok"}},
            failure_rule={"equals": {"path": "status", "value": "expired"}},
            trigger_task_id=task["id"],
        )
    )

    return engine, runtime_root, task


def test_repair_service_open_browser_marks_ticket_and_locks_profile(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_risk_context(tmp_path)
    service = RepairService(engine=engine, runtime_root=runtime_root)

    tickets = service.list_tickets()
    assert len(tickets) == 1

    result = service.open_browser(tickets[0]["ticket_code"], repaired_by="operator-A")

    with Session(engine) as session:
        ticket = session.execute(select(ManualRepairTicket)).scalar_one()
        profile = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == task["profile_key"])).scalar_one()

    assert result["status"] == "BROWSER_OPENED"
    assert ticket.status == "BROWSER_OPENED"
    assert profile.is_locked is True


def test_repair_service_verify_success_restores_task_profile_and_closes_ticket(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_risk_context(tmp_path)
    service = RepairService(
        engine=engine,
        runtime_root=runtime_root,
        health_check_executor=lambda *_args, **_kwargs: {"status": "PASS"},
    )
    ticket_code = service.list_tickets()[0]["ticket_code"]
    service.open_browser(ticket_code, repaired_by="operator-A")

    result = service.verify(ticket_code, repaired_by="operator-A")

    with Session(engine) as session:
        ticket = session.execute(select(ManualRepairTicket)).scalar_one()
        profile = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == task["profile_key"])).scalar_one()
        task_row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.task_code == task["task_code"])).scalar_one()

    assert result["status"] == "CLOSED"
    assert ticket.status == "CLOSED"
    assert profile.status == "READY"
    assert profile.is_locked is False
    assert task_row.status == "VALID"


def test_repair_service_verify_failure_keeps_task_risk_and_marks_ticket_failed(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_risk_context(tmp_path)
    service = RepairService(
        engine=engine,
        runtime_root=runtime_root,
        health_check_executor=lambda *_args, **_kwargs: {"status": "FAIL"},
    )
    ticket_code = service.list_tickets()[0]["ticket_code"]
    service.open_browser(ticket_code, repaired_by="operator-A")

    result = service.verify(ticket_code, repaired_by="operator-A")

    with Session(engine) as session:
        ticket = session.execute(select(ManualRepairTicket)).scalar_one()
        task_row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.task_code == task["task_code"])).scalar_one()

    assert result["status"] == "FAILED"
    assert ticket.status == "FAILED"
    assert task_row.status == "RISK"


def test_repair_service_close_ticket_unlocks_profile_and_keeps_task_risk(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_risk_context(tmp_path)
    service = RepairService(engine=engine, runtime_root=runtime_root)
    ticket_code = service.list_tickets()[0]["ticket_code"]
    service.open_browser(ticket_code, repaired_by="operator-A")

    result = service.close_ticket(ticket_code, repaired_by="operator-A")

    with Session(engine) as session:
        ticket = session.execute(select(ManualRepairTicket)).scalar_one()
        profile = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == task["profile_key"])).scalar_one()
        task_row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.task_code == task["task_code"])).scalar_one()

    assert result["status"] == "CLOSED"
    assert ticket.status == "CLOSED"
    assert ticket.closed_at is not None
    assert profile.is_locked is False
    assert profile.status == "RISK"
    assert task_row.status == "RISK"
