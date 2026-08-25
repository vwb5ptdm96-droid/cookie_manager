from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.database import Base
from app.models import load_models


def build_alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[3]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_alembic_upgrade_matches_current_orm_schema(tmp_path: Path) -> None:
    load_models()
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    config = build_alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    for table_name, model_table in Base.metadata.tables.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        expected_columns = set(model_table.columns.keys())
        assert actual_columns == expected_columns

    indexes = inspector.get_indexes("task_run_log")
    assert any(index["name"] == "ix_task_run_log_run_id" for index in indexes)

    with engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version")).scalar_one()

    assert version == ScriptDirectory.from_config(config).get_current_head()
