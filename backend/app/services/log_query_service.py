from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session

from app.models.run_log import TaskRunLog


class LogQueryService:
    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine

    def list_logs(
        self,
        *,
        run_type: str | None = None,
        status: str | None = None,
        task_id: int | None = None,
        check_id: int | None = None,
        ticket_id: int | None = None,
        health_task_code: str | None = None,
        keyword: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> dict[str, object]:
        statement: Select[tuple[TaskRunLog]] = select(TaskRunLog)
        if run_type:
            statement = statement.where(TaskRunLog.run_type == run_type)
        if status:
            statement = statement.where(TaskRunLog.status == status)
        if task_id is not None:
            statement = statement.where(TaskRunLog.task_id == task_id)
        if check_id is not None:
            statement = statement.where(TaskRunLog.check_id == check_id)
        if ticket_id is not None:
            statement = statement.where(TaskRunLog.ticket_id == ticket_id)
        if health_task_code:
            statement = statement.where(TaskRunLog.title.ilike(f"%{health_task_code}%"))
        if keyword:
            like_value = f"%{keyword}%"
            statement = statement.where((TaskRunLog.title.ilike(like_value)) | (TaskRunLog.message.ilike(like_value)))
        if start_at is not None:
            statement = statement.where(TaskRunLog.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(TaskRunLog.created_at <= end_at)

        statement = statement.order_by(TaskRunLog.created_at.desc(), TaskRunLog.id.desc()).limit(100)

        with Session(self.engine) as session:
            rows = session.execute(statement).scalars().all()

        return {
            "items": [
                {
                    "run_id": row.run_id,
                    "run_type": row.run_type,
                    "task_id": row.task_id,
                    "check_id": row.check_id,
                    "ticket_id": row.ticket_id,
                    "status": row.status,
                    "title": row.title,
                    "message": row.message,
                    "log_file_path": row.log_file_path,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        }
