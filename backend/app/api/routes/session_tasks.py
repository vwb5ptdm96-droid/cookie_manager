from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.session_task import (
    SessionTaskListResponse,
    SessionTaskResponse,
    SessionTaskToggleRequest,
    SessionTaskUpsertRequest,
)
from app.services.session_task_service import SessionTaskPayload, SessionTaskService


router = APIRouter(tags=["session-tasks"])


def build_session_task_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> SessionTaskService:
    engine: Engine = session_factory.kw["bind"]
    return SessionTaskService(engine=engine, runtime_root=runtime_root)


@router.get("/session-tasks")
def list_session_tasks(service: SessionTaskService = Depends(build_session_task_service)) -> dict[str, object]:
    data = SessionTaskListResponse(items=[SessionTaskResponse.model_validate(item) for item in service.list_tasks()])
    return success_response(data.model_dump())


@router.post("/session-tasks")
def create_session_task(
    payload: SessionTaskUpsertRequest,
    service: SessionTaskService = Depends(build_session_task_service),
) -> dict[str, object]:
    result = service.create_task(SessionTaskPayload(**payload.model_dump()))
    return success_response(SessionTaskResponse.model_validate(result).model_dump())


@router.put("/session-tasks/{task_code}")
def update_session_task(
    task_code: str,
    payload: SessionTaskUpsertRequest,
    service: SessionTaskService = Depends(build_session_task_service),
) -> dict[str, object]:
    result = service.update_task(task_code, SessionTaskPayload(**payload.model_dump()))
    return success_response(SessionTaskResponse.model_validate(result).model_dump())


@router.post("/session-tasks/{task_code}/execute")
def execute_session_task(
    task_code: str,
    service: SessionTaskService = Depends(build_session_task_service),
) -> dict[str, object]:
    result = service.execute_task(task_code)
    return success_response(SessionTaskResponse.model_validate(result).model_dump())


@router.post("/session-tasks/{task_code}/toggle")
def toggle_session_task(
    task_code: str,
    payload: SessionTaskToggleRequest,
    service: SessionTaskService = Depends(build_session_task_service),
) -> dict[str, object]:
    result = service.toggle_task(task_code, enabled=payload.enabled)
    return success_response(SessionTaskResponse.model_validate(result).model_dump())
