from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session_factory
from app.core.database import Base
from app.main import app
from app.models.env_check import EnvCheckResult
from app.models.health_check import HealthCheckConfig
from app.models.profile_registry import ProfileRegistry
from app.models.repair_ticket import ManualRepairTicket
from app.models.run_log import TaskRunLog
from app.models.session_task import SessionMaintenanceTask


def seed_phase7_data(engine, runtime_root: Path) -> int:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "profiles" / "ks" / "demo-user").mkdir(parents=True, exist_ok=True)
    (runtime_root / "scripts" / "uploaded").mkdir(parents=True, exist_ok=True)
    (runtime_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (runtime_root / "logs").mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        session.add(
            SessionMaintenanceTask(
                task_code="task_001",
                task_name="快手店铺会话维护",
                channel="KUAISHOU",
                mobile_phone="13800000001",
                account_alias="demo-shop",
                related_dns='["s.kwaixiaodian.com"]',
                script_code="maintain_ks",
                profile_key="profile_001",
                schedule_type="MANUAL",
                schedule_value="manual",
                script_config="{}",
                status="VALID",
                enabled=True,
                last_run_status="SUCCESS",
                last_run_id="run_001",
                last_artifact_dir=str(runtime_root / "artifacts" / "tasks" / "run_001"),
            )
        )
        session.flush()
        task_id = session.query(SessionMaintenanceTask.id).filter_by(task_code="task_001").scalar()

        session.add(
            ProfileRegistry(
                profile_key="profile_001",
                relative_path="profiles/ks/demo-user",
                status="READY",
                is_locked=False,
            )
        )
        check_row = HealthCheckConfig(
            check_code="check_001",
            check_name="店铺主页登录态检测",
            cookie_table="ods_cookie_playwright",
            channel="KUAISHOU",
            shop_name="demo-shop",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
            method="GET",
            check_url="https://example.test/health",
            success_rule='{"status_code": 200}',
            failure_rule='{"status_code": 401}',
            trigger_task_id=task_id,
            status="PASS",
            last_result_message="health check passed",
            enabled=True,
        )
        session.add(check_row)
        session.flush()
        session.add(
            ManualRepairTicket(
                ticket_code="ticket_001",
                task_code="task_001",
                profile_key="profile_001",
                risk_type="SMS",
                status="OPEN",
                risk_message="需要短信验证",
            )
        )
        session.add(
            TaskRunLog(
                run_id="run_001",
                run_type="TASK",
                task_id=task_id,
                status="SUCCESS",
                title="快手店铺会话维护",
                message="维护任务执行成功",
                log_file_path=str(runtime_root / "logs" / "task-run.log"),
            )
        )
        session.add(
            TaskRunLog(
                run_id="check_001",
                run_type="CHECK",
                task_id=task_id,
                check_id=check_row.id,
                status="FAIL",
                title="店铺主页登录态检测",
                message="检测失败并触发维护",
                log_file_path=str(runtime_root / "logs" / "check-run.log"),
            )
        )
        session.add(
            EnvCheckResult(
                check_code="runtime_root",
                status="PASS",
                summary="运行目录可访问",
            )
        )
        session.commit()
        return task_id


def test_phase7_routes_dashboard_environment_deploy_and_logs(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    testing_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    runtime_root = tmp_path / "runtime"
    task_id = seed_phase7_data(engine, runtime_root)

    app.dependency_overrides[get_session_factory] = lambda: testing_session_factory
    app.state.runtime_root = runtime_root

    try:
        with TestClient(app) as client:
            dashboard_response = client.get("/api/dashboard")
            execute_environment_response = client.post("/api/environment/checks/execute")
            latest_environment_response = client.get("/api/environment/checks/latest")
            deploy_response = client.get("/api/deploy/config")
            logs_response = client.get("/api/logs", params={"run_type": "TASK", "status": "SUCCESS", "keyword": "维护"})
            associated_logs_response = client.get("/api/logs", params={"task_id": task_id})

        assert dashboard_response.status_code == 200
        dashboard_payload = dashboard_response.json()["data"]
        assert dashboard_payload["stats"]["tasks"] == 1
        assert dashboard_payload["stats"]["profiles"] == 1
        assert dashboard_payload["stats"]["checks"] == 1
        assert dashboard_payload["stats"]["pending_repairs"] == 1
        assert dashboard_payload["recent_logs"][0]["run_type"] in {"TASK", "CHECK"}
        assert dashboard_payload["recent_checks"][0]["check_code"] == "check_001"

        assert execute_environment_response.status_code == 200
        environment_payload = execute_environment_response.json()["data"]
        assert environment_payload["items"]
        assert any(item["check_code"] == "database_connection" for item in environment_payload["items"])

        assert latest_environment_response.status_code == 200
        latest_payload = latest_environment_response.json()["data"]
        assert latest_payload["items"]

        assert deploy_response.status_code == 200
        deploy_payload = deploy_response.json()["data"]
        assert deploy_payload["runtime_root"] == str(runtime_root)
        assert "start_backend.bat" in deploy_payload["startup_command"]
        assert deploy_payload["current_user"]
        assert deploy_payload["current_user_hint"]
        assert deploy_payload["directories"]["logs"].endswith("logs")

        assert logs_response.status_code == 200
        logs_payload = logs_response.json()["data"]
        assert len(logs_payload["items"]) == 1
        assert logs_payload["items"][0]["run_type"] == "TASK"
        assert logs_payload["items"][0]["status"] == "SUCCESS"
        assert logs_payload["items"][0]["task_id"] == task_id

        assert associated_logs_response.status_code == 200
        associated_logs_payload = associated_logs_response.json()["data"]
        assert len(associated_logs_payload["items"]) == 2
        assert all(item["task_id"] == task_id for item in associated_logs_payload["items"])
    finally:
        app.dependency_overrides.clear()
