from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.response import success_response
from app.schemas.cookie_sync_task import (
    CookieSyncTaskCreateRequest,
    CookieSyncTaskListResponse,
    CookieSyncTaskResponse,
    CookieSyncTaskToggleRequest,
    CookieSyncTaskUpdateRequest,
)
from app.services.cookie_sync_task_service import CookieSyncTaskService

router = APIRouter(tags=["cookie-sync-tasks"])


def build_cookie_sync_task_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> CookieSyncTaskService:
    engine: Engine = session_factory.kw["bind"]
    return CookieSyncTaskService(engine=engine)


@router.get("/cookie-sync-tasks")
def list_cookie_sync_tasks(
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    data = CookieSyncTaskListResponse(
        items=[CookieSyncTaskResponse.model_validate(item) for item in service.list_tasks()]
    )
    return success_response(data.model_dump())


@router.get("/cookie-sync-tasks/{cookie_sync_task_code}")
def get_cookie_sync_task(
    cookie_sync_task_code: str,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.get_task(cookie_sync_task_code)
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.post("/cookie-sync-tasks")
def create_cookie_sync_task(
    payload: CookieSyncTaskCreateRequest,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.create_task(payload.model_dump())
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.patch("/cookie-sync-tasks/{cookie_sync_task_code}")
def update_cookie_sync_task(
    cookie_sync_task_code: str,
    payload: CookieSyncTaskUpdateRequest,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.update_task(
        cookie_sync_task_code, payload.model_dump(exclude_unset=True)
    )
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.post("/cookie-sync-tasks/{cookie_sync_task_code}/toggle")
def toggle_cookie_sync_task(
    cookie_sync_task_code: str,
    payload: CookieSyncTaskToggleRequest,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.toggle_task(code=cookie_sync_task_code, enabled=payload.enabled)
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.post("/cookie-sync-tasks/{cookie_sync_task_code}/check")
def execute_cookie_sync_check(
    cookie_sync_task_code: str,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.execute_check(cookie_sync_task_code)
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.post("/cookie-sync-tasks/{cookie_sync_task_code}/repair")
def execute_cookie_sync_repair(
    cookie_sync_task_code: str,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    """手动执行扩展采集：不经过检测，直接下发采集任务进入 SYNCING（Spec REQ-007 AC-005）。"""
    result = service.execute_sync_repair(cookie_sync_task_code)
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.post("/cookie-sync-tasks/{cookie_sync_task_code}/clone")
def clone_cookie_sync_task(
    cookie_sync_task_code: str,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    result = service.clone_task(cookie_sync_task_code)
    return success_response(CookieSyncTaskResponse.model_validate(result).model_dump())


@router.delete("/cookie-sync-tasks/{cookie_sync_task_code}")
def delete_cookie_sync_task(
    cookie_sync_task_code: str,
    service: CookieSyncTaskService = Depends(build_cookie_sync_task_service),
) -> dict[str, object]:
    service.delete_task(cookie_sync_task_code)
    return success_response(None)
