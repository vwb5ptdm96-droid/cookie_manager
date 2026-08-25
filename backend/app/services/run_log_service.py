from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.models.run_log import TaskRunLog

BEIJING_TZ = timezone(timedelta(hours=8))


class RunLogService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def write(
        self,
        *,
        run_id: str,
        run_type: str,
        task_id: int | None = None,
        check_id: int | None = None,
        ticket_id: int | None = None,
        status: str,
        title: str,
        message: str,
        log_file_path: str | None = None,
    ) -> TaskRunLog:
        row = TaskRunLog(
            run_id=run_id,
            run_type=run_type,
            task_id=task_id,
            check_id=check_id,
            ticket_id=ticket_id,
            status=status,
            title=title,
            message=message,
            log_file_path=log_file_path,
            created_at=datetime.now(BEIJING_TZ).replace(tzinfo=None),
        )

        with Session(self.engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)

        if log_file_path:
            path = Path(log_file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{status}] {title}: {message}\n")

        return row
