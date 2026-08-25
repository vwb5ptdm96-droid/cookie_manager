from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.run_log import TaskRunLog
from app.services.run_log_service import RunLogService


def test_run_log_service_writes_database_row_and_log_file(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)

    service = RunLogService(engine=engine)
    log_file = tmp_path / "runtime.log"

    service.write(
        run_id="run_001",
        run_type="SYSTEM",
        task_id=11,
        check_id=22,
        ticket_id=33,
        status="SUCCESS",
        title="bootstrap",
        message="phase 2 ready",
        log_file_path=str(log_file),
    )

    with Session(engine) as session:
        row = session.execute(select(TaskRunLog)).scalar_one()

    assert row.run_id == "run_001"
    assert row.task_id == 11
    assert row.check_id == 22
    assert row.ticket_id == 33
    assert row.title == "bootstrap"
    assert log_file.read_text(encoding="utf-8").strip().endswith("phase 2 ready")
