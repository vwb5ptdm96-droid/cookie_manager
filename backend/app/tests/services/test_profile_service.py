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
