from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.run_log import TaskRunLog
from app.models.script_registry import ScriptRegistry
from app.services.health_task_service import HealthTaskService


def build_service(tmp_path: Path) -> HealthTaskService:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'health.db'}",
        connect_args={"timeout": 30},
    )
    Base.metadata.create_all(engine)
    service = HealthTaskService(engine=engine, runtime_root=tmp_path / "runtime")
    service.legacy_cookie_service = MagicMock()
    return service


def seed_data(service: HealthTaskService) -> str:
    """写入脚本、Profile、HealthTask，返回 task_code。"""
    with Session(service.engine) as session:
        script = ScriptRegistry(
            script_code="maintain_ks",
            script_name="快手维护",
            script_type="MAINTAIN",
            platform="KUAISHOU",
            version="1.0.0",
            script_dir="scripts/uploaded/maintain_ks/1.0.0",
            main_file="main.py",
            enabled=True,
        )
        session.add(script)
        session.flush()

        profile = ProfileRegistry(
            profile_key="profile_001",
            relative_path="profiles/ks/demo",
            status="READY",
            is_locked=False,
        )
        session.add(profile)
        session.flush()

        task = HealthTask(
            health_task_code="ht_001",
            health_task_name="快手检测",
            enabled=True,
            channel="KUAISHOU",
            shop_name="demo",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
            check_url="https://example.com/check",
            http_method="GET",
            auto_repair_enabled=True,
            repair_script_id=script.id,
            repair_directory_id=profile.id,
            repair_run_mode="HEADLESS",
            status="PENDING",
        )
        session.add(task)
        session.commit()
        return "ht_001"


def _bare_service() -> HealthTaskService:
    """构造不依赖 DB 的实例，仅用于纯逻辑方法测试。"""
    return HealthTaskService.__new__(HealthTaskService)


def test_mask_sensitive_hides_cookie_token_and_phone() -> None:
    service = _bare_service()

    masked = service._mask_sensitive(
        '{"data": {"token": "abc123secret", "cookie": "sessionid=xyz", "mobile": "13800138000"}, "Set-Cookie": "sid=secret"}'
    )

    assert "abc123secret" not in masked
    assert "sessionid=xyz" not in masked
    assert "13800138000" not in masked
    assert "***" in masked


def test_mask_sensitive_keeps_normal_text() -> None:
    service = _bare_service()

    masked = service._mask_sensitive('{"status": "ok", "message": "检测通过"}')

    assert "检测通过" in masked
    assert "status" in masked


def test_match_rule_status_code() -> None:
    service = _bare_service()

    assert service._match_rule('{"status_code": 200}', 200, {"a": 1}) is True
    assert service._match_rule('{"status_code": 200}', 500, {"a": 1}) is False


def test_match_rule_contains() -> None:
    service = _bare_service()

    assert service._match_rule('{"contains": "success"}', 200, {"msg": "operation success"}) is True
    assert service._match_rule('{"contains": "fail"}', 200, {"msg": "operation success"}) is False


@patch("app.services.health_task_service.kill_chrome_for_profile")
@patch("app.services.health_task_service.kill_chrome_on_port")
@patch("app.services.health_task_service.send_feishu_notification")
def test_repair_risk_sends_feishu_and_writes_repair_log(
    mock_feishu: MagicMock,
    mock_kill_port: MagicMock,
    mock_kill_profile: MagicMock,
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    task_code = seed_data(service)

    # mock 脚本文件存在
    script_dir = tmp_path / "runtime" / "scripts" / "uploaded" / "maintain_ks" / "1.0.0"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "main.py").write_text("print('hi')", encoding="utf-8")

    # mock executor 返回 RISK
    service.executor = MagicMock()
    service.executor.execute.return_value = {
        "status": "RISK",
        "risk_type": "SMS",
        "message": "出现短信验证",
        "exit_code": 3,
        "log_path": str(script_dir / "run.log"),
    }

    result = service.execute_repair(task_code)

    # 状态回到 PENDING
    assert result["status"] == "PENDING"
    assert result["last_run_status"] == "RISK"
    # 飞书通知发送
    mock_feishu.assert_called_once()
    call_kwargs = mock_feishu.call_args.kwargs
    assert "风控" in call_kwargs["title"]
    # REPAIR 日志写入
    with Session(service.engine) as session:
        log = session.query(TaskRunLog).filter_by(run_type="REPAIR").first()
        assert log is not None
        assert log.status == "RISK"
        assert "短信验证" in log.message
        # 目录锁已释放
        profile = session.query(ProfileRegistry).filter_by(profile_key="profile_001").first()
        assert profile.is_locked is False


@patch("app.services.health_task_service.kill_chrome_for_profile")
@patch("app.services.health_task_service.kill_chrome_on_port")
@patch("app.services.health_task_service.send_feishu_notification")
def test_repair_success_writes_repair_log_no_feishu(
    mock_feishu: MagicMock,
    mock_kill_port: MagicMock,
    mock_kill_profile: MagicMock,
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    task_code = seed_data(service)

    script_dir = tmp_path / "runtime" / "scripts" / "uploaded" / "maintain_ks" / "1.0.0"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "main.py").write_text("print('hi')", encoding="utf-8")

    service.executor = MagicMock()
    service.executor.execute.return_value = {
        "status": "SUCCESS",
        "message": "执行成功",
        "exit_code": 0,
        "log_path": str(script_dir / "run.log"),
    }

    result = service.execute_repair(task_code)

    assert result["status"] == "PASS"
    # SUCCESS 不触发飞书提醒
    mock_feishu.assert_not_called()
    with Session(service.engine) as session:
        log = session.query(TaskRunLog).filter_by(run_type="REPAIR").first()
        assert log is not None
        assert log.status == "SUCCESS"
        profile = session.query(ProfileRegistry).filter_by(profile_key="profile_001").first()
        assert profile.is_locked is False
