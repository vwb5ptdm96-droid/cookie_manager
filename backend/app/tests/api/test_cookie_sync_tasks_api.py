from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.api.routes.cookie_sync_tasks import build_cookie_sync_task_service
from app.core.database import Base
from app.main import app
from app.services.cookie_sync_task_service import CookieSyncTaskService


class FakeNotifier:
    """记录飞书调用，测试断言用，不真发网络请求。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, title: str, message: str, *, fields: dict[str, str] | None = None) -> bool:
        self.calls.append({"title": title, "message": message, "fields": fields or {}})
        return True


def _setup(tmp_path: Path, monkeypatch):
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
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
    testing_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: testing_factory
    notifier = FakeNotifier()
    # 注入测试 service：cookie_engine 指向测试库，notifier 关闭飞书
    app.dependency_overrides[build_cookie_sync_task_service] = lambda: CookieSyncTaskService(
        engine=engine, cookie_engine=engine, notifier=notifier
    )

    def fake_http(**kwargs) -> dict[str, object]:
        return {"status_code": 500, "body": "failure"}

    monkeypatch.setattr(
        "app.services.cookie_sync_task_service.perform_health_request", fake_http
    )
    return engine, notifier


def _create_payload(**overrides) -> dict[str, object]:
    payload = {
        "cookie_sync_task_name": "店铺A cookie 检测",
        "channel": "WEIXIN",
        "shop_name": "shop-a",
        "dns": "store.weixin.qq.com",
        "check_url": "https://store.weixin.qq.com/check",
        "http_method": "GET",
        # fake_http 返回 500，命中失败规则 → 检测失败路径
        "failure_rule": '{"status_code": 500}',
    }
    payload.update(overrides)
    return payload


def test_crud_flow(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path, monkeypatch)
    try:
        with TestClient(app) as client:
            # 空列表
            assert client.get("/api/cookie-sync-tasks").json()["data"]["items"] == []

            # 创建
            r = client.post("/api/cookie-sync-tasks", json=_create_payload())
            assert r.status_code == 200
            created = r.json()["data"]
            code = created["cookie_sync_task_code"]
            assert code.startswith("cst_")
            assert created["status"] == "PENDING"

            # 列表
            items = client.get("/api/cookie-sync-tasks").json()["data"]["items"]
            assert len(items) == 1

            # 详情
            got = client.get(f"/api/cookie-sync-tasks/{code}").json()["data"]
            assert got["cookie_sync_task_name"] == "店铺A cookie 检测"

            # 更新
            upd = client.patch(
                f"/api/cookie-sync-tasks/{code}",
                json={"sync_wait_timeout_seconds": 300, "cookie_sync_task_name": "改名"},
            ).json()["data"]
            assert upd["sync_wait_timeout_seconds"] == 300
            assert upd["cookie_sync_task_name"] == "改名"

            # 启停
            off = client.post(f"/api/cookie-sync-tasks/{code}/toggle", json={"enabled": False}).json()["data"]
            assert off["status"] == "DISABLED"
            on = client.post(f"/api/cookie-sync-tasks/{code}/toggle", json={"enabled": True}).json()["data"]
            assert on["status"] == "PENDING"

            # 克隆
            clone = client.post(f"/api/cookie-sync-tasks/{code}/clone").json()["data"]
            assert clone["cookie_sync_task_code"] != code
            assert clone["cookie_sync_task_name"] == "改名 (副本)"

            # 删除
            assert client.delete(f"/api/cookie-sync-tasks/{clone['cookie_sync_task_code']}").status_code == 200
            assert len(client.get("/api/cookie-sync-tasks").json()["data"]["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_execute_check_via_api_fails_without_mapping(tmp_path: Path, monkeypatch) -> None:
    _, notifier = _setup(tmp_path, monkeypatch)
    try:
        with TestClient(app) as client:
            code = client.post("/api/cookie-sync-tasks", json=_create_payload()).json()["data"][
                "cookie_sync_task_code"
            ]
            r = client.post(f"/api/cookie-sync-tasks/{code}/check")
            assert r.status_code == 200
            data = r.json()["data"]
            assert data["status"] == "FAIL"
            assert "无对应采集映射" in data["last_result_message"]
            assert len(notifier.calls) == 1
    finally:
        app.dependency_overrides.clear()


def test_execute_repair_via_api(tmp_path: Path, monkeypatch) -> None:
    """AC-005：手动执行扩展采集接口。有映射 → SYNCING；无映射 → 409 NO_MAPPING。"""
    _setup(tmp_path, monkeypatch)
    try:
        with TestClient(app) as client:
            # 建映射 + 采集任务
            client.post(
                "/api/cookie-sync-mappings",
                json={
                    "worker_id": "同事A",
                    "domain": "store.weixin.qq.com",
                    "channel": "WEIXIN",
                    "shop_name": "shop-a",
                    "dns": "store.weixin.qq.com",
                },
            )
            code = client.post("/api/cookie-sync-tasks", json=_create_payload()).json()["data"][
                "cookie_sync_task_code"
            ]

            # 有映射 → 直接进入 SYNCING
            r = client.post(f"/api/cookie-sync-tasks/{code}/repair")
            assert r.status_code == 200
            data = r.json()["data"]
            assert data["status"] == "SYNCING"
            assert "已下发采集任务" in data["check_detail"]

            # 无映射任务 → 409 NO_MAPPING（不同业务键，不命中上面创建的映射）
            no_map_code = client.post(
                "/api/cookie-sync-tasks",
                json=_create_payload(
                    cookie_sync_task_name="无映射任务",
                    channel="TAOBAO",
                    dns="item.taobao.com",
                ),
            ).json()["data"]["cookie_sync_task_code"]
            r2 = client.post(f"/api/cookie-sync-tasks/{no_map_code}/repair")
            assert r2.status_code == 409
            assert r2.json()["error_code"] == "NO_MAPPING"
    finally:
        app.dependency_overrides.clear()


def test_execute_check_disabled_task_400(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path, monkeypatch)
    try:
        with TestClient(app) as client:
            code = client.post("/api/cookie-sync-tasks", json=_create_payload()).json()["data"][
                "cookie_sync_task_code"
            ]
            client.post(f"/api/cookie-sync-tasks/{code}/toggle", json={"enabled": False})
            r = client.post(f"/api/cookie-sync-tasks/{code}/check")
            assert r.status_code == 400
            assert r.json()["error_code"] == "TASK_DISABLED"
    finally:
        app.dependency_overrides.clear()
