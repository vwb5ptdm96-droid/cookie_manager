from app.core.database import Base
from app.models import load_models


def test_metadata_contains_expected_tables() -> None:
    load_models()

    expected_tables = {
        "health_task",
        "script_run",
        "script_registry",
        "profile_registry",
        "task_run_log",
        "env_check_result",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))

