import json
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.health_check import HealthCheckConfig
from app.models.session_task import SessionMaintenanceTask
from app.services.health_check_service import HealthCheckPayload, HealthCheckService
from app.services.profile_service import ProfilePayload, ProfileService
from app.services.script_service import ScriptService
from app.services.session_task_service import SessionTaskPayload, SessionTaskService


SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
artifact_dir.joinpath("result.json").write_text(json.dumps({"status": "SUCCESS", "message": "ok"}), encoding="utf-8")
"""


def bootstrap_dependencies(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'checks.db'}")
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
                    cookie text,
                    headers text,
                    str_cookie text,
                    file varchar(64),
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into ods_cookie_playwright (
                    channel, shop_name, mobile_phone, DNS, str_cookie, headers, file
                ) values (
                    :channel, :shop_name, :mobile_phone, :dns, :str_cookie, :headers, :file
                )
                """
            ),
            {
                "channel": "KUAISHOU",
                "shop_name": "demo-shop",
                "mobile_phone": "13800000001",
                "dns": "s.kwaixiaodian.com",
                "str_cookie": "sid=1",
                "headers": json.dumps({"X-Legacy": "legacy-token"}),
                "file": "profile_ks_138",
            },
        )

    profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
    script_service = ScriptService(engine=engine, runtime_root=runtime_root)
    task_service = SessionTaskService(engine=engine, runtime_root=runtime_root)

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
            script_config={"expected_status": "SUCCESS"},
        )
    )
    return engine, runtime_root, task


def test_health_check_service_pass_result(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_dependencies(tmp_path)
    service = HealthCheckService(
        engine=engine,
        runtime_root=runtime_root,
        request_runner=lambda **_: {"status_code": 200, "body": {"status": "ok"}},
    )

    created = service.create_check(
        HealthCheckPayload(
            check_name="店铺主页登录态检测",
            cookie_table="ods_cookie_playwright",
            channel="KUAISHOU",
            shop_name="demo-shop",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
            method="GET",
            check_url="http://example.test/health",
            request_headers={"X-Request": "custom"},
            success_rule={"equals": {"path": "status", "value": "ok"}},
            failure_rule={"equals": {"path": "status", "value": "expired"}},
            trigger_task_id=task["id"],
        )
    )
    result = service.execute_check(created["check_code"])

    assert result["status"] == "PASS"
    assert result["triggered_task_code"] is None


def test_health_check_service_failure_marks_task_expired_and_triggers_execute(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_dependencies(tmp_path)
    triggered = {"called": False}

    def fake_task_executor(task_id: int, task_code: str) -> dict[str, object]:
      triggered["called"] = True
      with Session(engine) as session:
          row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.id == task_id)).scalar_one()
          assert row.status == "EXPIRED"
      return {"task_code": task_code}

    service = HealthCheckService(
        engine=engine,
        runtime_root=runtime_root,
        request_runner=lambda **_: {"status_code": 200, "body": {"status": "expired"}},
        task_executor=fake_task_executor,
    )
    created = service.create_check(
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
    result = service.execute_check(created["check_code"])

    assert result["status"] == "FAIL"
    assert result["triggered_task_code"] == task["task_code"]
    assert triggered["called"] is True


def test_health_check_service_failure_records_failure(tmp_path: Path) -> None:
    engine, runtime_root, task = bootstrap_dependencies(tmp_path)
    service = HealthCheckService(
        engine=engine,
        runtime_root=runtime_root,
        request_runner=lambda **_: {"status_code": 401, "body": {"status": "expired"}},
    )
    created = service.create_check(
        HealthCheckPayload(
            check_name="店铺主页登录态检测",
            cookie_table="ods_cookie_playwright",
            channel="KUAISHOU",
            shop_name="demo-shop",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
            method="GET",
            check_url="http://example.test/health",
            failure_rule={"status_code": 401},
            trigger_task_id=task["id"],
        )
    )
    result = service.execute_check(created["check_code"])

    with Session(engine) as session:
        row = session.execute(select(HealthCheckConfig).where(HealthCheckConfig.check_code == created["check_code"])).scalar_one()

    assert result["status"] == "FAIL"
    assert row.status == "FAIL"
