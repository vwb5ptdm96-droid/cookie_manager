from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.database import Base
from app.main import app


def test_phase3_routes_create_profile_and_upload_script(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    testing_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True)

    app.dependency_overrides[get_session_factory] = lambda: testing_session_factory
    app.state.runtime_root = runtime_root

    try:
        with TestClient(app) as client:
            profile_response = client.post(
                "/api/profiles",
                json={
                    "profile_key": "profile_001",
                    "task_id": None,
                    "relative_path": "profiles/ks/demo-user",
                },
            )
            script_response = client.post(
                "/api/scripts/upload",
                data={
                    "script_name": "快手维护脚本",
                    "script_code": "maintain_ks",
                    "script_type": "MAINTAIN",
                    "platform": "KUAISHOU",
                    "version": "1.0.0",
                    "description": "demo script",
                },
                files={"script_file": ("main.py", b"print('hello')\n", "text/x-python")},
            )
            list_response = client.get("/api/scripts")

        assert profile_response.status_code == 200
        assert profile_response.json()["data"]["task_id"] is None
        assert profile_response.json()["data"]["absolute_path"].endswith("runtime\\profiles\\ks\\demo-user")
        assert script_response.status_code == 200
        assert script_response.json()["data"]["script_code"] == "maintain_ks"
        assert script_response.json()["data"]["main_file"] == "main.py"
        assert list_response.status_code == 200
        assert list_response.json()["data"]["items"][0]["script_code"] == "maintain_ks"
    finally:
        app.dependency_overrides.clear()
