import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session_factory
from app.api.routes.cookie_sync import build_cookie_sync_service
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.services.cookie_sync_service import CookieSyncService


def _setup(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
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
                    headers text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
    testing_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: testing_factory
    # 注入 cookie_engine，避免测试写云端 MySQL
    app.dependency_overrides[build_cookie_sync_service] = lambda: CookieSyncService(engine=engine, cookie_engine=engine)
    return engine


def _seed_mapping(engine) -> None:
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
        session.commit()


def _get_ods_row(engine):
    with engine.connect() as connection:
        return connection.execute(text("select * from ods_cookie_playwright")).mappings().first()


def _seed_ods_row(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into ods_cookie_playwright (channel, shop_name, mobile_phone, DNS, cookie, str_cookie) "
                "values ('WEIXIN', 'shop-a', '13900000002', 'store.weixin.qq.com', '{}', 'sid=old')"
            )
        )


def test_ping_no_auth(tmp_path: Path) -> None:
    _setup(tmp_path)
    try:
        with TestClient(app) as client:
            r = client.get("/api/ping")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_full_chain_request_tasks_report(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    _seed_mapping(engine)
    try:
        with TestClient(app) as client:
            req = client.post(
                "/api/request",
                json={"domains": ["store.weixin.qq.com"], "worker_ids": ["同事A"]},
            )
            assert req.status_code == 200
            data = req.json()
            assert data["task_id"]
            assert data["tasks"][0]["worker"] == "同事A"
            assert data["tasks"][0]["domains"] == ["store.weixin.qq.com"]

            tasks = client.get("/api/tasks", params={"worker_id": "同事A"})
            assert tasks.status_code == 200
            assert tasks.json()["tasks"][0]["task_id"] == data["task_id"]

            report = client.post(
                f"/api/tasks/{data['task_id']}/report",
                json={
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                    "worker_id": "同事A",
                },
            )
            assert report.status_code == 200
            assert report.json()["stored"] == 1
            assert report.json()["worker_id"] == "同事A"

        row = _get_ods_row(engine)
        assert row is not None
        assert row["str_cookie"] == "sid=abc"
    finally:
        app.dependency_overrides.clear()


def test_auth_required_when_key_configured(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    monkeypatch.setenv("COOKIE_SYNC_API_KEY", "secret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            no_key = client.post("/api/request", json={"domains": ["store.weixin.qq.com"]})
            assert no_key.status_code == 401
            assert no_key.json()["success"] is False
            assert no_key.json()["error_code"] == "UNAUTHORIZED"

            wrong_key = client.post(
                "/api/request",
                json={"domains": ["store.weixin.qq.com"]},
                headers={"X-API-Key": "wrong"},
            )
            assert wrong_key.status_code == 401
            assert wrong_key.json()["error_code"] == "UNAUTHORIZED"

            ok = client.post(
                "/api/request",
                json={"domains": ["store.weixin.qq.com"]},
                headers={"X-API-Key": "secret"},
            )
            assert ok.status_code == 200

            # ping 不受鉴权影响
            assert client.get("/api/ping").status_code == 200
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_report_unknown_task_returns_404(tmp_path: Path) -> None:
    _setup(tmp_path)
    try:
        with TestClient(app) as client:
            r = client.post("/api/tasks/task_nonexistent/report", json={"cookies": []})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_direct_upload_via_api(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    _seed_mapping(engine)
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/cookies",
                json={
                    "domains": ["store.weixin.qq.com"],
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                    "worker_id": "同事A",
                },
            )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "stored": 1, "worker_id": "同事A"}
        row = _get_ods_row(engine)
        assert row is not None
        assert row["str_cookie"] == "sid=abc"
    finally:
        app.dependency_overrides.clear()


def test_tasks_empty_worker_returns_broadcast_only(tmp_path: Path) -> None:
    _setup(tmp_path)
    try:
        with TestClient(app) as client:
            client.post("/api/request", json={"domains": ["store.weixin.qq.com"], "worker_ids": ["同事A"]})
            client.post("/api/request", json={"domains": ["store.weixin.qq.com"]})  # 广播

            # 不带 worker_id：只返回广播任务，不暴露定向任务
            no_worker = client.get("/api/tasks")
            assert no_worker.status_code == 200
            assert [t["worker"] for t in no_worker.json()["tasks"]] == ["any"]

            # 带 worker_id：定向 + 广播
            with_worker = client.get("/api/tasks", params={"worker_id": "同事A"})
            assert {t["worker"] for t in with_worker.json()["tasks"]} == {"同事A", "any"}
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_inserts_new(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [
                        {"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"},
                        {"name": "token", "value": "xyz", "domain": "store.weixin.qq.com"},
                    ],
                },
            )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "stored": 2, "is_new": True}
        row = _get_ods_row(engine)
        assert row is not None
        assert row["str_cookie"] == "sid=abc; token=xyz"
        assert row["cookie"] == (
            '[{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}, '
            '{"name": "token", "value": "xyz", "domain": "store.weixin.qq.com"}]'
        )
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_updates_existing(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    _seed_ods_row(engine)
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "new_value", "domain": "store.weixin.qq.com"}],
                },
            )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "stored": 1, "is_new": False}
        row = _get_ods_row(engine)
        assert row is not None
        assert row["str_cookie"] == "sid=new_value"
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_with_headers_writes_headers_col(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                    "headers": {"User-Agent": "Mozilla/5.0", "X-Token": "tok123"},
                },
            )
        assert r.status_code == 200
        row = _get_ods_row(engine)
        assert row is not None
        assert json.loads(row["headers"]) == {"User-Agent": "Mozilla/5.0", "X-Token": "tok123"}
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_update_with_headers_overwrites_col(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    _seed_ods_row(engine)
    try:
        with TestClient(app) as client:
            # 更新带 headers：headers 列覆盖
            r1 = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                    "headers": {"User-Agent": "Chrome/130"},
                },
            )
            assert r1.status_code == 200
            assert r1.json()["is_new"] is False
            assert json.loads(_get_ods_row(engine)["headers"]) == {"User-Agent": "Chrome/130"}

            # 更新不带 headers：headers 列保留旧值，不覆盖为空
            r2 = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "def", "domain": "store.weixin.qq.com"}],
                },
            )
            assert r2.status_code == 200
            row = _get_ods_row(engine)
            assert json.loads(row["headers"]) == {"User-Agent": "Chrome/130"}
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_empty_cookies_returns_400(tmp_path: Path) -> None:
    _setup(tmp_path)
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "mobile_phone": "13900000002",
                    "dns": "store.weixin.qq.com",
                    "cookies": [],
                },
            )
        assert r.status_code == 400
        assert r.json()["error_code"] == "EMPTY_COOKIES"
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_blank_channel_or_dns_rejected(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    try:
        with TestClient(app) as client:
            blank_channel = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "",
                    "shop_name": "shop-a",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                },
            )
            assert blank_channel.status_code == 422

            blank_dns = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "dns": "",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                },
            )
            assert blank_dns.status_code == 422
        # 空定位键不得落库
        assert _get_ods_row(engine) is None
    finally:
        app.dependency_overrides.clear()


def test_manual_upload_auth_required_when_key_configured(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    monkeypatch.setenv("COOKIE_SYNC_API_KEY", "secret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            no_key = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                },
            )
            assert no_key.status_code == 401
            assert no_key.json()["error_code"] == "UNAUTHORIZED"

            wrong_key = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                },
                headers={"X-API-Key": "wrong"},
            )
            assert wrong_key.status_code == 401
            assert wrong_key.json()["error_code"] == "UNAUTHORIZED"

            ok = client.post(
                "/api/cookies/manual",
                json={
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "dns": "store.weixin.qq.com",
                    "cookies": [{"name": "sid", "value": "abc", "domain": "store.weixin.qq.com"}],
                },
                headers={"X-API-Key": "secret"},
            )
            assert ok.status_code == 200
            assert ok.json()["is_new"] is True
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
