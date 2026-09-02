from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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


def test_session_task_routes_create_and_execute(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    testing_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True)

    app.dependency_overrides[get_session_factory] = lambda: testing_session_factory
    app.state.runtime_root = runtime_root

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
            create_response = client.post(
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
            task_code = create_response.json()["data"]["task_code"]
            update_response = client.put(
                f"/api/session-tasks/{task_code}",
                json={
                    "task_name": "快手店铺会话维护-已更新",
                    "channel": "KUAISHOU",
                    "mobile_phone": "13800000002",
                    "account_alias": "demo-shop-updated",
                    "related_dns": ["s.kwaixiaodian.com", "seller.kwaixiaodian.com"],
                    "script_code": "maintain_ks",
                    "profile_key": "profile_001",
                    "schedule_type": "MANUAL",
                    "schedule_value": "manual",
                    "script_config": {"expected_status": "SUCCESS", "retry": 1},
                },
            )
            toggle_response = client.post(f"/api/session-tasks/{task_code}/toggle", json={"enabled": False})
            disabled_execute_response = client.post(f"/api/session-tasks/{task_code}/execute")
            reenable_response = client.post(f"/api/session-tasks/{task_code}/toggle", json={"enabled": True})
            run_response = client.post(f"/api/session-tasks/{task_code}/execute")
            list_response = client.get("/api/session-tasks")

        assert create_response.status_code == 200
        assert update_response.status_code == 200
        assert update_response.json()["data"]["task_name"] == "快手店铺会话维护-已更新"
        assert update_response.json()["data"]["mobile_phone"] == "13800000002"
        assert toggle_response.status_code == 200
        assert toggle_response.json()["data"]["status"] == "DISABLED"
        assert disabled_execute_response.status_code == 409
        assert disabled_execute_response.json()["error_code"] == "TASK_DISABLED"
        assert reenable_response.status_code == 200
        assert run_response.status_code == 200
        assert run_response.json()["data"]["status"] == "VALID"
        assert list_response.status_code == 200
        assert list_response.json()["data"]["items"][0]["task_code"] == task_code
    finally:
        app.dependency_overrides.clear()
