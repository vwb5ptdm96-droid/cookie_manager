from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.database import Base
from app.main import app


MAINTAIN_SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
artifact_dir.joinpath("result.json").write_text(json.dumps({"status": "RISK", "message": "risk happened"}), encoding="utf-8")
"""

MANUAL_SCRIPT_SOURCE = b"""
import json
import os
from pathlib import Path
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
artifact_dir.joinpath("result.json").write_text(json.dumps({"status": "SUCCESS", "message": "browser opened"}), encoding="utf-8")
"""


def seed_repair_route_context(client: TestClient) -> str:
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
        files={"script_file": ("main.py", MAINTAIN_SCRIPT_SOURCE, "text/x-python")},
    )
    client.post(
        "/api/scripts/upload",
        data={
            "script_name": "快手人工修复脚本",
            "script_code": "manual_ks",
            "script_type": "MANUAL",
            "platform": "KUAISHOU",
            "version": "1.0.0",
            "description": "",
        },
        files={"script_file": ("repair.py", MANUAL_SCRIPT_SOURCE, "text/x-python")},
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
            "script_config": {"expected_status": "RISK"},
        },
    )
    task_code = task_response.json()["data"]["task_code"]
    task_id = task_response.json()["data"]["id"]

    client.post(
        "/api/health-checks",
        json={
            "check_name": "店铺主页登录态检测",
            "cookie_table": "ods_cookie_playwright",
            "channel": "KUAISHOU",
            "shop_name": "demo-shop",
            "mobile_phone": "13800000001",
            "dns": "s.kwaixiaodian.com",
            "method": "GET",
            "check_url": "http://example.test/health",
            "request_headers": {},
            "request_body": {},
            "success_rule": {"status_code": 200},
            "failure_rule": {"status_code": 401},
            "trigger_task_id": task_id,
        },
    )
    client.post(f"/api/session-tasks/{task_code}/execute")

    tickets_response = client.get("/api/repairs")
    return tickets_response.json()["data"]["items"][0]["ticket_code"]


def build_client(tmp_path):
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

    app.dependency_overrides[get_session_factory] = lambda: testing_session_factory
    app.state.runtime_root = runtime_root
    return TestClient(app)


def test_repair_routes_open_and_verify(tmp_path) -> None:
    try:
        with build_client(tmp_path) as client:
            ticket_code = seed_repair_route_context(client)
            open_response = client.post(f"/api/repairs/{ticket_code}/open", json={"repaired_by": "operator-A"})
            verify_response = client.post(f"/api/repairs/{ticket_code}/verify", json={"repaired_by": "operator-A"})

        assert open_response.status_code == 200
        assert open_response.json()["data"]["status"] == "BROWSER_OPENED"
        assert verify_response.status_code == 200
        assert verify_response.json()["data"]["status"] in {"CLOSED", "FAILED"}
    finally:
        app.dependency_overrides.clear()


def test_repair_routes_close_ticket(tmp_path) -> None:
    try:
        with build_client(tmp_path) as client:
            ticket_code = seed_repair_route_context(client)
            open_response = client.post(f"/api/repairs/{ticket_code}/open", json={"repaired_by": "operator-A"})
            close_response = client.post(f"/api/repairs/{ticket_code}/close", json={"repaired_by": "operator-B"})

        assert open_response.status_code == 200
        assert close_response.status_code == 200
        assert close_response.json()["data"]["status"] == "CLOSED"
    finally:
        app.dependency_overrides.clear()
