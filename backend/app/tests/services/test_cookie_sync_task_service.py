from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.models.cookie_sync_task import CookieSyncTask
from app.services.cookie_sync_service import CookieSyncService
from app.services.cookie_sync_task_service import CookieSyncTaskService, beijing_now


class FakeNotifier:
    """记录飞书调用，测试断言用，不真发网络请求。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, title: str, message: str, *, fields: dict[str, str] | None = None) -> bool:
        self.calls.append({"title": title, "message": message, "fields": fields or {}})
        return True


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
                    headers text,
                    str_cookie text,
                    create_time text,
                    update_time text,
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


def _make_service(
    tmp_path: Path, monkeypatch, fake_http_status: int = 500
) -> tuple[CookieSyncTaskService, object, FakeNotifier]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'task.db'}")
    Base.metadata.create_all(engine)
    _create_legacy_table(engine)
    _seed_legacy_cookie(engine)
    notifier = FakeNotifier()

    def fake_http(**kwargs) -> dict[str, object]:
        return {"status_code": fake_http_status, "body": "failure"}

    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.perform_health_request", fake_http
    )
    service = CookieSyncTaskService(engine=engine, cookie_engine=engine, notifier=notifier)
    return service, engine, notifier


def _add_mapping(engine, worker_id: str = "同事A") -> None:
    with Session(engine) as session:
        session.add(
            CookieSyncMapping(
                worker_id=worker_id,
                domain="store.weixin.qq.com",
                channel="WEIXIN",
                shop_name="shop-a",
                mobile_phone="13900000002",
                dns="store.weixin.qq.com",
                remark="test",
            )
        )
        session.commit()


def _create_task(service: CookieSyncTaskService, **overrides) -> dict[str, object]:
    payload = {
        "cookie_sync_task_name": "店铺A cookie 检测",
        "cookie_table": "ods_cookie_playwright",
        "channel": "WEIXIN",
        "shop_name": "shop-a",
        "mobile_phone": "13900000002",
        "dns": "store.weixin.qq.com",
        "check_url": "https://store.weixin.qq.com/check",
        "http_method": "GET",
        "success_rule": '{"status_code": 200}',
        "failure_rule": '{"status_code": 500}',
        "cron_expression": None,
        "sync_wait_timeout_seconds": 180,
    }
    payload.update(overrides)
    return service.create_task(payload)


def _get_latest_job(engine) -> CookieSyncJob | None:
    with Session(engine) as session:
        return session.query(CookieSyncJob).order_by(CookieSyncJob.id.desc()).first()


def test_mask_url_redacts_query_token(tmp_path: Path, monkeypatch) -> None:
    """复审遗留：裸 URL query 的 token/api_key 等必须脱敏（_mask_sensitive 对裸 URL 无效）。"""
    service, _, _ = _make_service(tmp_path, monkeypatch, fake_http_status=200)

    masked = service._mask_url("https://x.com/check?token=abc123secret&page=1")
    assert masked == "https://x.com/check?token=***&page=1"
    masked2 = service._mask_url("https://x.com/check?api_key=XYZ&sign=abc")
    assert "XYZ" not in masked2 and "abc" not in masked2
    # 无关参数不误伤
    assert "page=1" in masked


def test_create_task_success(tmp_path: Path, monkeypatch) -> None:
    service, _, _ = _make_service(tmp_path, monkeypatch)

    created = _create_task(service)

    assert created["cookie_sync_task_code"].startswith("cst_")
    assert created["status"] == "PENDING"
    assert created["sync_wait_timeout_seconds"] == 180
    assert service.list_tasks()[0]["cookie_sync_task_name"] == "店铺A cookie 检测"


def test_execute_check_pass(tmp_path: Path, monkeypatch) -> None:
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=200)

    task = _create_task(service, success_rule='{"status_code": 200}', failure_rule=None)
    result = service.execute_check(task["cookie_sync_task_code"])

    assert result["status"] == "PASS"
    assert result["last_run_status"] == "SUCCESS"
    assert "命中成功规则" in result["last_result_message"]
    assert notifier.calls == []  # 通过不通知


def test_execute_check_fail_no_mapping_fails_and_notifies(tmp_path: Path, monkeypatch) -> None:
    """AC-003：检测失败且无映射 → FAIL + 飞书，不触发采集。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)

    task = _create_task(service)
    result = service.execute_check(task["cookie_sync_task_code"])

    assert result["status"] == "FAIL"
    assert "无对应采集映射" in result["last_result_message"]
    assert _get_latest_job(engine) is None  # 未下发采集任务
    assert len(notifier.calls) == 1
    assert "失败" in notifier.calls[0]["title"]


def test_execute_check_fail_with_mapping_enters_syncing(tmp_path: Path, monkeypatch) -> None:
    """AC-002 前半：检测失效 + 存在映射 → 下发定向采集任务 → SYNCING。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    _add_mapping(engine)

    task = _create_task(service)
    result = service.execute_check(task["cookie_sync_task_code"])

    assert result["status"] == "SYNCING"
    assert result["sync_deadline_at"] is not None
    job = _get_latest_job(engine)
    assert job is not None
    assert job.worker_id == "同事A"
    assert job.domains == '["store.weixin.qq.com"]'
    assert job.source_task_id == task["id"]
    assert job.status == "pending"
    assert notifier.calls == []  # 等待上报阶段不通知


def test_full_loop_upload_then_recheck_passes(tmp_path: Path, monkeypatch) -> None:
    """AC-002 完整：失效→SYNCING→扩展上报写回→复检通过→PASS。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    _add_mapping(engine)

    task = _create_task(service)
    service.execute_check(task["cookie_sync_task_code"])
    job = _get_latest_job(engine)
    assert job is not None

    # 模拟扩展上报：写回 ods 表
    sync_service = CookieSyncService(engine=engine, cookie_engine=engine)
    report = sync_service.handle_report(
        job.task_id,
        cookies=[{"name": "sid", "value": "new-value", "domain": "store.weixin.qq.com"}],
        worker_id="同事A",
    )
    assert report["stored"] == 1
    # MAJOR-1：上报写回成功应记录采集任务最近同步时间
    with Session(engine) as session:
        row = session.query(CookieSyncTask).filter_by(id=task["id"]).one()
        assert row.last_sync_at is not None

    # 上报完成，复检时 HTTP 恢复成功
    def fake_http_ok(**kwargs) -> dict[str, object]:
        return {"status_code": 200, "body": "ok"}

    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.perform_health_request", fake_http_ok
    )
    result = service.recheck_after_sync(task["id"])

    assert result["status"] == "PASS"
    assert "复检通过" in result["last_result_message"]
    assert result["sync_deadline_at"] is None
    assert notifier.calls == []


def test_recheck_still_fails_after_upload(tmp_path: Path, monkeypatch) -> None:
    """上报写回后复检仍失败 → FAIL + 飞书。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    _add_mapping(engine)

    task = _create_task(service)
    service.execute_check(task["cookie_sync_task_code"])
    job = _get_latest_job(engine)

    sync_service = CookieSyncService(engine=engine, cookie_engine=engine)
    sync_service.handle_report(
        job.task_id,
        cookies=[{"name": "sid", "value": "new", "domain": "store.weixin.qq.com"}],
        worker_id="同事A",
    )

    # 复检仍返回 500
    result = service.recheck_after_sync(task["id"])

    assert result["status"] == "FAIL"
    assert "复检仍失败" in result["last_result_message"]
    assert len(notifier.calls) == 1


def test_sync_timeout_fails_and_notifies(tmp_path: Path, monkeypatch) -> None:
    """AC-004：等待上报超时 → FAIL + 飞书。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    _add_mapping(engine)

    task = _create_task(service, sync_wait_timeout_seconds=1)
    service.execute_check(task["cookie_sync_task_code"])

    # 把 deadline 改成过去，模拟超时
    with Session(engine) as session:
        row = session.query(CookieSyncTask).filter_by(id=task["id"]).one()
        row.sync_deadline_at = beijing_now() - __import__("datetime").timedelta(seconds=5)
        session.commit()

    result = service.fail_on_timeout(task["id"])

    assert result["status"] == "FAIL"
    assert "等待扩展上报超时" in result["last_result_message"]
    assert len(notifier.calls) == 1


def test_recheck_and_timeout_skipped_when_not_syncing(tmp_path: Path, monkeypatch) -> None:
    """MAJOR-4 守卫：非 SYNCING 状态下复检/超时处理应跳过，不覆盖任务状态。"""
    service, engine, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)

    # 任务初始为 PENDING，直接调复检/超时 → 跳过
    task = _create_task(service)
    recheck = service.recheck_after_sync(task["id"])
    assert recheck["status"] == "PENDING"
    timeout = service.fail_on_timeout(task["id"])
    assert timeout["status"] == "PENDING"
    assert notifier.calls == []

    # FAIL 状态下调复检 → 保持 FAIL 不被覆盖
    _add_mapping(engine)
    task2 = _create_task(service)
    service.execute_check(task2["cookie_sync_task_code"])
    assert service.get_task(task2["cookie_sync_task_code"])["status"] == "SYNCING"
    service.fail_on_timeout(task2["id"])
    recheck_again = service.recheck_after_sync(task2["id"])
    assert recheck_again["status"] == "FAIL"  # 已非 SYNCING，跳过复检，保持 FAIL
    assert len(notifier.calls) == 1  # 仅超时通知一次，复检跳过不再通知


def test_update_toggle_clone_delete(tmp_path: Path, monkeypatch) -> None:
    service, _, notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    task = _create_task(service)

    updated = service.update_task(
        task["cookie_sync_task_code"], {"cookie_sync_task_name": "改名后", "sync_wait_timeout_seconds": 300}
    )
    assert updated["cookie_sync_task_name"] == "改名后"
    assert updated["sync_wait_timeout_seconds"] == 300

    toggled_off = service.toggle_task(task["cookie_sync_task_code"], enabled=False)
    assert toggled_off["status"] == "DISABLED"

    toggled_on = service.toggle_task(task["cookie_sync_task_code"], enabled=True)
    assert toggled_on["status"] == "PENDING"

    cloned = service.clone_task(task["cookie_sync_task_code"])
    assert cloned["cookie_sync_task_name"].endswith("(副本)")
    assert cloned["cookie_sync_task_code"] != task["cookie_sync_task_code"]

    service.delete_task(cloned["cookie_sync_task_code"])
    with pytest.raises(AppError):
        service.get_task(cloned["cookie_sync_task_code"])


def test_disabled_task_check_rejected(tmp_path: Path, monkeypatch) -> None:
    service, _, _ = _make_service(tmp_path, monkeypatch, fake_http_status=200)
    task = _create_task(service)
    service.toggle_task(task["cookie_sync_task_code"], enabled=False)

    with pytest.raises(AppError) as exc:
        service.execute_check(task["cookie_sync_task_code"])
    assert exc.value.error_code == "TASK_DISABLED"
