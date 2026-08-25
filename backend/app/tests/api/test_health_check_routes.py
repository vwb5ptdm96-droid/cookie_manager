import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.database import Base
from app.main import app


SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
artifact_dir.joinpath("result.json").write_text(json.dumps({"status": "SUCCESS", "message": "ok"}), encoding="utf-8")
"""


class OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def test_health_check_routes_create_and_execute(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    testing_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
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
                "dns": "seller.kwaixiaodian.com",
                "str_cookie": "sid=2",
            },
        )

    app.dependency_overrides[get_session_factory] = lambda: testing_session_factory
    app.state.runtime_root = runtime_root

    server = ThreadingHTTPServer(("127.0.0.1", 0), OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with TestClient(app) as client:
            client.post(
                "/api/profiles",
                json={
                    "profile_key": "profile_001",
                    "relative_path": "profiles/ks/demo-user",
                },
            )
            client.post(
                "/api/scripts/upload",
                data={
                    "script_name": "快手维护脚本",
                    "script_code": "maintain_ks",
                    "script_type": "MAINTAIN",
                    "platform": "KUAISHOU",
                    "version": "1.0.0",
                    "description": "",
                },
                files={"script_file": ("main.py", SCRIPT_SOURCE, "text/x-python")},
            )
            task_response = client.post(
                "/api/session-tasks",
                json={
                    "task_name": "快手店铺会话维护",
                    "channel": "KUAISHOU",
                    "mobile_phone": "13800000001",
                    "account_alias": "demo-shop",
                    "related_dns": ["s.kwaixiaodian.com"],
                    "script_code": "maintain_ks",
                    "profile_key": "profile_001",
                    "schedule_type": "MANUAL",
                    "schedule_value": "manual",
                    "script_config": {"expected_status": "SUCCESS"},
                },
            )
            task_id = task_response.json()["data"]["id"]
            create_response = client.post(
                "/api/health-checks",
                json={
                    "check_name": "店铺主页登录态检测",
                    "cookie_table": "ods_cookie_playwright",
                    "channel": "KUAISHOU",
                    "shop_name": "demo-shop",
                    "mobile_phone": "13800000001",
                    "dns": "s.kwaixiaodian.com",
                    "method": "GET",
                    "check_url": f"http://127.0.0.1:{server.server_address[1]}/health",
                    "request_headers": {},
                    "request_body": {},
                    "success_rule": {"equals": {"path": "status", "value": "ok"}},
                    "failure_rule": {"equals": {"path": "status", "value": "expired"}},
                    "trigger_task_id": task_id,
                },
            )
            check_code = create_response.json()["data"]["check_code"]
            update_response = client.put(
                f"/api/health-checks/{check_code}",
                json={
                    "check_name": "店铺主页登录态检测-已更新",
                    "cookie_table": "ods_cookie_playwright",
                    "channel": "KUAISHOU",
                    "shop_name": "demo-shop",
                    "mobile_phone": "13800000001",
                    "dns": "seller.kwaixiaodian.com",
                    "method": "GET",
                    "check_url": f"http://127.0.0.1:{server.server_address[1]}/health",
                    "request_headers": {"X-Request": "updated"},
                    "request_body": {"source": "updated"},
                    "success_rule": {"equals": {"path": "status", "value": "ok"}},
                    "failure_rule": {"equals": {"path": "status", "value": "expired"}},
                    "trigger_task_id": task_id,
                },
            )
            toggle_response = client.post(f"/api/health-checks/{check_code}/toggle", json={"enabled": False})
            disabled_execute_response = client.post(f"/api/health-checks/{check_code}/execute")
            reenable_response = client.post(f"/api/health-checks/{check_code}/toggle", json={"enabled": True})
            execute_response = client.post(f"/api/health-checks/{check_code}/execute")
            execute_all_response = client.post("/api/health-checks/execute-all")

        assert create_response.status_code == 200
        assert update_response.status_code == 200
        assert update_response.json()["data"]["check_name"] == "店铺主页登录态检测-已更新"
        assert update_response.json()["data"]["dns"] == "seller.kwaixiaodian.com"
        assert toggle_response.status_code == 200
        assert toggle_response.json()["data"]["status"] == "DISABLED"
        assert disabled_execute_response.status_code == 409
        assert disabled_execute_response.json()["error_code"] == "HEALTH_CHECK_DISABLED"
        assert reenable_response.status_code == 200
        assert execute_response.status_code == 200
        assert execute_response.json()["data"]["status"] == "PASS"
        assert execute_all_response.status_code == 200
        assert len(execute_all_response.json()["data"]["items"]) == 1
    finally:
        server.shutdown()
        app.dependency_overrides.clear()
