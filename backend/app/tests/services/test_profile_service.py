from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.session_task import SessionMaintenanceTask
from app.services.profile_service import ProfilePayload, ProfileService


def build_service(tmp_path: Path) -> ProfileService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profiles.db'}")
    Base.metadata.create_all(engine)
    return ProfileService(engine=engine, runtime_root=tmp_path / "runtime")


def seed_task(service: ProfileService) -> int:
    with Session(service.engine) as session:
        row = SessionMaintenanceTask(
            task_code="task_001",
            task_name="快手维护任务",
            channel="KUAISHOU",
            mobile_phone="13800000001",
            account_alias="demo-shop",
            related_dns='["s.kwaixiaodian.com"]',
            script_code="maintain_ks",
            profile_key="profile_001",
            schedule_type="MANUAL",
            schedule_value="manual",
            script_config="{}",
            status="INIT",
            enabled=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def test_profile_service_persists_relative_path_and_returns_absolute_preview(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    task_id = seed_task(service)

    result = service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            task_id=task_id,
            relative_path="profiles/ks/demo-user",
            note="first profile",
        )
    )

    assert result["profile_key"] == "profile_001"
    assert result["task_id"] == task_id
    assert result["relative_path"] == "profiles/ks/demo-user"
    assert result["absolute_path"].endswith("runtime\\profiles\\ks\\demo-user")
    assert result["status"] == "READY"


def test_profile_service_rejects_lock_conflict(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            task_id=None,
            relative_path="profiles/ks/demo-user",
        )
    )

    service.lock("profile_001", owner="task-A")

    with pytest.raises(AppError) as exc_info:
        service.lock("profile_001", owner="task-B")

    assert exc_info.value.error_code == "PROFILE_LOCKED"


def test_profile_service_verify_moves_profile_to_ready(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    runtime_profile = tmp_path / "runtime" / "profiles" / "ks" / "demo-user"
    runtime_profile.mkdir(parents=True)

    service.upsert(
        ProfilePayload(
            profile_key="profile_001",
            task_id=None,
            relative_path="profiles/ks/demo-user",
        )
    )
    service.mark_risk("profile_001")

    result = service.verify("profile_001")

    assert result["status"] == "READY"
    assert result["lock_owner"] is None


def test_profile_service_rejects_unknown_task_binding(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.upsert(
            ProfilePayload(
                profile_key="profile_001",
                task_id=999,
                relative_path="profiles/ks/demo-user",
            )
        )

    assert exc_info.value.error_code == "TASK_NOT_FOUND"
