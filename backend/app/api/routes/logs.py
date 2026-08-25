from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.response import success_response
from app.services.log_query_service import LogQueryService


router = APIRouter(tags=["logs"])


def build_log_query_service(session_factory: sessionmaker = Depends(get_session_factory)) -> LogQueryService:
    engine: Engine = session_factory.kw["bind"]
    return LogQueryService(engine=engine)


@router.get("/logs")
def list_logs(
    run_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    task_id: int | None = Query(default=None),
    check_id: int | None = Query(default=None),
    ticket_id: int | None = Query(default=None),
    health_task_code: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    service: LogQueryService = Depends(build_log_query_service),
) -> dict[str, object]:
    return success_response(
        service.list_logs(
            run_type=run_type,
            status=status,
            task_id=task_id,
            check_id=check_id,
            ticket_id=ticket_id,
            health_task_code=health_task_code,
            keyword=keyword,
            start_at=start_at,
            end_at=end_at,
        )
    )
