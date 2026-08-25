from app.core.database import Base
from app.models import load_models


def test_metadata_contains_expected_tables() -> None:
    load_models()

    expected_tables = {
        "session_maintenance_task",
        "health_check_config",
        "script_registry",
        "profile_registry",
        "manual_repair_ticket",
        "task_run_log",
        "env_check_result",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))

