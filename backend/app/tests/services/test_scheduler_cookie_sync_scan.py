from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.models.cookie_sync_task import CookieSyncTask
from app.services.cookie_sync_task_service import beijing_now
from app.services.scheduler_service import HealthTaskScheduler


def _create_legacy_table(engine) -> None:
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
                    str_cookie text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )


def _seed_legacy_cookie(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into ods_cookie_playwright "
                "(channel, shop_name, mobile_phone, DNS, cookie, str_cookie) "
                "values (:c, :s, :m, :d, :cookie, :str_cookie)"
            ),
            {
                "c": "WEIXIN",
                "s": "shop-a",
                "m": "13900000002",
                "d": "store.weixin.qq.com",
                "cookie": "[]",
                "str_cookie": "old=1",
            },
        )


def _make_env(tmp_path: Path, monkeypatch, http_status: int = 500):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'scan.db'}")
    Base.metadata.create_all(engine)
    _create_legacy_table(engine)
    _seed_legacy_cookie(engine)

    with Session(engine) as session:
        session.add(
            CookieSyncMapping(
                worker_id="同事A",
                domain="store.weixin.qq.com",
                channel="WEIXIN",
                shop_name="shop-a",
                mobile_phone="13900000002",
                dns="store.weixin.qq.com",
                remark="test",
            )
        )
        task = CookieSyncTask(
            cookie_sync_task_code="cst_scan001",
            cookie_sync_task_name="扫描采集任务",
            enabled=True,
            cookie_table="ods_cookie_playwright",
            channel="WEIXIN",
            shop_name="shop-a",
            mobile_phone="13900000002",
            dns="store.weixin.qq.com",
            check_url="https://store.weixin.qq.com/check",
            http_method="GET",
            failure_rule='{"status_code": 500}',
            sync_wait_timeout_seconds=180,
            status="PENDING",
        )
        session.add(task)
        session.commit()

    # 规避云端 MySQL + 真实飞书 + 真实 HTTP
    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.create_mysql_engine", lambda: None
    )
    notifier_calls: list[dict[str, object]] = []

    def fake_notifier(title, message, *, fields=None):
        notifier_calls.append({"title": title, "message": message})
        return True

    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.send_feishu_notification", fake_notifier
    )
    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.perform_health_request",
        lambda **kwargs: {"status_code": http_status, "body": "resp"},
    )
    scheduler = HealthTaskScheduler(engine=engine, runtime_root=tmp_path / "runtime")
    return engine, scheduler, notifier_calls


def test_scan_triggers_check_and_enters_syncing(tmp_path: Path, monkeypatch) -> None:
    """调度扫描：检测失败 + 有映射 → 下发采集 → SYNCING。"""
    engine, scheduler, _ = _make_env(tmp_path, monkeypatch, http_status=500)

    scheduler._scan_cookie_sync_tasks()

    with Session(engine) as session:
        task = session.query(CookieSyncTask).filter_by(cookie_sync_task_code="cst_scan001").one()
        assert task.status == "SYNCING"
        assert task.sync_deadline_at is not None
        job = session.query(CookieSyncJob).filter_by(source_task_id=task.id).first()
        assert job is not None
        assert job.worker_id == "同事A"
        assert job.status == "pending"


def test_scan_rechecks_when_job_done(tmp_path: Path, monkeypatch) -> None:
    """调度扫描：扩展上报完成（job done）→ 复检恢复 PASS。"""
    engine, scheduler, _ = _make_env(tmp_path, monkeypatch, http_status=500)
    scheduler._scan_cookie_sync_tasks()

    # 模拟扩展上报完成
    with Session(engine) as session:
        task = session.query(CookieSyncTask).filter_by(cookie_sync_task_code="cst_scan001").one()
        job = session.query(CookieSyncJob).filter_by(source_task_id=task.id).first()
        job.status = "done"
        job.finished_at = beijing_now()
        session.commit()

    # 复检时 HTTP 恢复成功
    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.perform_health_request",
        lambda **kwargs: {"status_code": 200, "body": "ok"},
    )
    scheduler._scan_cookie_sync_tasks()

    with Session(engine) as session:
        task = session.query(CookieSyncTask).filter_by(cookie_sync_task_code="cst_scan001").one()
        assert task.status == "PASS"
        assert task.sync_deadline_at is None


def test_scan_fails_when_sync_timed_out(tmp_path: Path, monkeypatch) -> None:
    """调度扫描：SYNCING 且 deadline 已过 → FAIL + 飞书。"""
    engine, scheduler, notifier_calls = _make_env(tmp_path, monkeypatch, http_status=500)
    scheduler._scan_cookie_sync_tasks()

    # 把 deadline 改成过去，模拟等待超时
    with Session(engine) as session:
        task = session.query(CookieSyncTask).filter_by(cookie_sync_task_code="cst_scan001").one()
        task.sync_deadline_at = beijing_now() - timedelta(seconds=5)
        session.commit()

    scheduler._scan_cookie_sync_tasks()

    with Session(engine) as session:
        task = session.query(CookieSyncTask).filter_by(cookie_sync_task_code="cst_scan001").one()
        assert task.status == "FAIL"
        assert "超时" in task.last_result_message
    assert len(notifier_calls) == 1
