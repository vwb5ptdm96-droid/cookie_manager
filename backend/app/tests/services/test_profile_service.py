from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.errors import AppError
from app.services.profile_service import ProfilePayload, ProfileService


def build_service(tmp_path: Path) -> ProfileService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profiles.db'}")
    Base.metadata.create_all(engine)
    return ProfileService(engine=engine, runtime_root=tmp_path / "runtime")


def test_profile_service_persists_relative_path_and_returns_absolute_preview(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    result = service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            relative_path="profiles/ks/demo-user",
            note="first profile",
        )
    )

    assert result["profile_key"] == "profile_001"
    assert result["relative_path"] == "profiles/ks/demo-user"
    assert result["absolute_path"].endswith("runtime\\profiles\\ks\\demo-user")
    assert result["status"] == "READY"


def test_profile_service_rejects_lock_conflict(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            relative_path="profiles/ks/demo-user",
        )
    )

    service.lock("profile_001", owner="run-task-A")

    with pytest.raises(AppError) as exc_info:
        service.lock("profile_001", owner="run-task-B")

    assert exc_info.value.error_code == "PROFILE_LOCKED"


def test_profile_service_verify_moves_profile_to_ready(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    runtime_profile = tmp_path / "runtime" / "profiles" / "ks" / "demo-user"
    runtime_profile.mkdir(parents=True)

    service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            relative_path="profiles/ks/demo-user",
        )
    )
    service.mark_risk("profile_001")

    result = service.verify("profile_001")

    assert result["status"] == "READY"
    assert result["lock_owner"] is None


def test_profile_service_persists_debug_port(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    result = service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            relative_path="profiles/ks/demo-user",
            debug_port=9223,
        )
    )

    assert result["debug_port"] == 9223


def test_profile_service_open_debug_rejects_locked_profile(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user"))
    service.lock("profile_001", owner="run-task-A")

    with pytest.raises(AppError) as exc_info:
        service.open_debug("profile_001")

    assert exc_info.value.error_code == "DIRECTORY_LOCKED"


def test_profile_service_open_debug_chrome_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user"))

    monkeypatch.setattr("app.services.profile_service.find_chrome_executable", lambda: None)

    with pytest.raises(AppError) as exc_info:
        service.open_debug("profile_001")

    assert exc_info.value.error_code == "CHROME_NOT_FOUND"


def test_profile_service_open_debug_already_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service(tmp_path)
    service.upsert(
        ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user", debug_port=9224)
    )

    monkeypatch.setattr("app.services.profile_service.find_chrome_executable", lambda: Path("C:/chrome.exe"))
    monkeypatch.setattr("app.services.profile_service.wait_for_cdp", lambda port, timeout=10.0: True)

    result = service.open_debug("profile_001")

    assert result["already_running"] is True
    assert result["port"] == 9224
    assert result["cdp_url"] == "http://127.0.0.1:9224"


def test_profile_service_close_debug_returns_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user"))

    killed: list[Path] = []
    monkeypatch.setattr("app.services.profile_service.kill_chrome_for_profile", lambda p: killed.append(p))
    monkeypatch.setattr("app.services.profile_service.kill_chrome_on_port", lambda p: pytest.fail("close 不应按端口杀，避免跨目录同端口误杀"))

    result = service.close_debug("profile_001")

    assert result["closed"] is True
    assert result["port"] == 9222  # 默认调试端口
    assert len(killed) == 1  # 只按 user-data-dir 精确清理


def test_profile_service_close_debug_rejects_locked_profile(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user"))
    service.lock("profile_001", owner="run-task-A")

    with pytest.raises(AppError) as exc_info:
        service.close_debug("profile_001")

    assert exc_info.value.error_code == "DIRECTORY_LOCKED"


def test_profile_service_open_debug_cdp_not_ready_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service(tmp_path)
    service.upsert(ProfilePayload(profile_key="profile_001", relative_path="profiles/ks/demo-user"))

    killed = {"profile": 0, "port": 0}
    monkeypatch.setattr("app.services.profile_service.find_chrome_executable", lambda: Path("C:/chrome.exe"))
    monkeypatch.setattr("app.services.profile_service.wait_for_cdp", lambda port, timeout=10.0: False)
    monkeypatch.setattr("app.services.profile_service.launch_chrome_debug", lambda p, port, c: None)
    monkeypatch.setattr(
        "app.services.profile_service.kill_chrome_for_profile",
        lambda p: killed.__setitem__("profile", killed["profile"] + 1),
    )
    monkeypatch.setattr(
        "app.services.profile_service.kill_chrome_on_port",
        lambda p: killed.__setitem__("port", killed["port"] + 1),
    )

    with pytest.raises(AppError) as exc_info:
        service.open_debug("profile_001")

    assert exc_info.value.error_code == "CDP_NOT_READY"
    assert killed["profile"] >= 1
    assert killed["port"] >= 1
