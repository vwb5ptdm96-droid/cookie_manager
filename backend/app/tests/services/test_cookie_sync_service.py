from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.services.cookie_sync_service import CookieSyncService


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


def _make_service(tmp_path: Path) -> tuple[CookieSyncService, object]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    _create_legacy_table(engine)
    # cookie_engine 注入测试库，避免测试写云端 MySQL
    service = CookieSyncService(engine=engine, cookie_engine=engine)
    return service, engine


def _add_mapping(
    engine,
    worker_id: str = "同事A",
    domain: str = "store.weixin.qq.com",
    channel: str = "WEIXIN",
    shop_name: str = "shop-a",
    dns: str = "store.weixin.qq.com",
) -> None:
    with Session(engine) as session:
        session.add(
            CookieSyncMapping(
                worker_id=worker_id,
                domain=domain,
                channel=channel,
                shop_name=shop_name,
                mobile_phone="13900000002",
                dns=dns,
                remark="test",
            )
        )
        session.commit()


def _get_ods_row(engine, channel: str, shop_name: str, mobile_phone: str, dns: str):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "select * from ods_cookie_playwright "
                "where channel=:c and shop_name=:s and mobile_phone=:m and DNS=:d"
            ),
            {"c": channel, "s": shop_name, "m": mobile_phone, "d": dns},
        ).mappings().first()


def test_create_request_directed_creates_job_per_worker(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)

    result = service.create_request(["store.weixin.qq.com"], ["同事A", "同事B"])

    assert result["status"] == "pending"
    assert len(result["tasks"]) == 2
    assert result["tasks"][0]["worker"] == "同事A"
    assert result["tasks"][1]["worker"] == "同事B"
    assert all(t["domains"] == ["store.weixin.qq.com"] for t in result["tasks"])


def test_create_request_broadcast_when_no_worker(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)

    result = service.create_request(["store.weixin.qq.com"], [])

    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["worker"] == "any"


def test_list_pending_tasks_directed_and_broadcast(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    service.create_request(["store.weixin.qq.com"], ["同事A"])
    service.create_request(["store.weixin.qq.com"], [])  # 广播
    service.create_request(["store.weixin.qq.com"], ["同事B"])

    tasks_a = service.list_pending_tasks("同事A")

    assert {t["worker"] for t in tasks_a} == {"同事A", "any"}  # 定向 + 广播，不含同事B
    assert len(service.list_pending_tasks()) == 3  # 不传 worker 返回全部


def test_handle_report_writes_via_mapping_and_marks_done(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    job = service.create_request(["store.weixin.qq.com"], ["同事A"])["tasks"][0]
    cookies = [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}]

    result = service.handle_report(job["task_id"], cookies, worker_id="同事A")

    assert result["ok"] is True
    assert result["stored"] == 1
    assert result["worker_id"] == "同事A"
    # 任务标记完成，不再出现在轮询
    assert job["task_id"] not in [t["task_id"] for t in service.list_pending_tasks("同事A")]
    # ods 表已按映射写入
    row = _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com")
    assert row is not None
    assert row["str_cookie"] == "sid=abc"
    assert '"name": "sid"' in row["cookie"]


def test_handle_report_unmapped_domain_dropped(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)  # 只映射 store.weixin.qq.com
    job = service.create_request(["other.example.com"], ["同事A"])["tasks"][0]
    cookies = [{"name": "a", "value": "1", "domain": "other.example.com"}]

    result = service.handle_report(job["task_id"], cookies, worker_id="同事A")

    assert result["stored"] == 0
    assert _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com") is None


def test_handle_report_directed_worker_takes_precedence(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    job = service.create_request(["store.weixin.qq.com"], ["同事A"])["tasks"][0]
    cookies = [{"name": "sid", "value": "xyz", "domain": "store.weixin.qq.com"}]

    # 上报 worker_id 与定向不一致，以定向为准
    result = service.handle_report(job["task_id"], cookies, worker_id="同事B")

    assert result["worker_id"] == "同事A"
    row = _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com")
    assert row is not None
    assert row["str_cookie"] == "sid=xyz"


def test_handle_direct_upload_writes_by_worker(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    cookies = [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}]

    result = service.handle_direct_upload(cookies, worker_id="同事A")

    assert result["stored"] == 1
    assert result["worker_id"] == "同事A"
    assert _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com") is not None


def test_handle_report_task_not_found(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.handle_report("task_nonexistent", [], None)

    assert exc.value.status_code == 404


def test_report_normalizes_leading_dot_domain(tmp_path: Path) -> None:
    """Chrome cookies 返回 .store.weixin.qq.com，映射配裸域名，应匹配写库。"""
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    job = service.create_request(["store.weixin.qq.com"], ["同事A"])["tasks"][0]
    cookies = [{"name": "sid", "value": "abc", "domain": ".store.weixin.qq.com"}]

    result = service.handle_report(job["task_id"], cookies, worker_id="同事A")

    assert result["stored"] == 1
    assert _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com") is not None


def test_mapping_with_leading_dot_matches_bare_domain(tmp_path: Path) -> None:
    """映射 domain 存成带前导点形式，上报裸域名也应命中。"""
    service, engine = _make_service(tmp_path)
    _add_mapping(engine, domain=".store.weixin.qq.com", dns="store.weixin.qq.com")
    cookies = [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}]

    result = service.handle_direct_upload(cookies, worker_id="同事A")

    assert result["stored"] == 1


def test_direct_upload_unmapped_dropped(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    cookies = [{"name": "a", "value": "1", "domain": "other.example.com"}]

    result = service.handle_direct_upload(cookies, worker_id="同事A")

    assert result["stored"] == 0
    assert _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com") is None


def test_broadcast_report_attributes_to_uploader(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    job = service.create_request(["store.weixin.qq.com"], [])["tasks"][0]  # 广播
    assert job["worker"] == "any"
    cookies = [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}]

    result = service.handle_report(job["task_id"], cookies, worker_id="同事A")

    assert result["worker_id"] == "同事A"
    assert job["task_id"] not in [t["task_id"] for t in service.list_pending_tasks()]
    assert _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com") is not None


def test_broadcast_report_unknown_fallback(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine, worker_id="unknown")
    job = service.create_request(["store.weixin.qq.com"], [])["tasks"][0]

    result = service.handle_report(job["task_id"], [{"name": "sid", "value": "a", "domain": "store.weixin.qq.com"}], None)

    assert result["worker_id"] == "unknown"


def test_str_cookie_joins_multiple_cookies(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    cookies = [
        {"name": "a", "value": "1", "domain": "store.weixin.qq.com"},
        {"name": "b", "value": "2", "domain": "store.weixin.qq.com"},
    ]

    result = service.handle_direct_upload(cookies, worker_id="同事A")

    assert result["stored"] == 2
    row = _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com")
    assert row["str_cookie"] == "a=1; b=2"


def test_cookie_without_value_stored_in_json_but_not_str(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    cookies = [
        {"name": "ok", "value": "1", "domain": "store.weixin.qq.com"},
        {"name": "broken", "domain": "store.weixin.qq.com"},  # 缺 value
    ]

    result = service.handle_direct_upload(cookies, worker_id="同事A")

    assert result["stored"] == 2  # 两条都写入 cookie JSON
    row = _get_ods_row(engine, "WEIXIN", "shop-a", "13900000002", "store.weixin.qq.com")
    assert row["str_cookie"] == "ok=1"  # str_cookie 只含有效 name=value
    assert "broken" in row["cookie"]  # 缺 value 的 cookie 仍在 JSON 里


def test_mapping_last_report_updated(tmp_path: Path) -> None:
    service, engine = _make_service(tmp_path)
    _add_mapping(engine)
    cookies = [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}]

    service.handle_direct_upload(cookies, worker_id="同事A")

    with Session(engine) as session:
        mapping = session.query(CookieSyncMapping).filter_by(worker_id="同事A", domain="store.weixin.qq.com").first()
        assert mapping.last_report_count == 1
        assert mapping.last_report_at is not None
