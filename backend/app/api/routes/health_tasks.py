from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.health_task import (
    HealthTaskCreateRequest,
    HealthTaskListResponse,
    HealthTaskResponse,
    HealthTaskToggleRequest,
    HealthTaskUpdateRequest,
)
from app.services.health_task_service import HealthTaskService

router = APIRouter(tags=["health-tasks"])


def build_health_task_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> HealthTaskService:
    engine: Engine = session_factory.kw["bind"]
    return HealthTaskService(engine=engine, runtime_root=runtime_root)


@router.get("/health-tasks")
def list_health_tasks(
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    data = HealthTaskListResponse(
        items=[HealthTaskResponse.model_validate(item) for item in service.list_tasks()]
    )
    return success_response(data.model_dump())


@router.get("/health-tasks/{health_task_code}")
def get_health_task(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.get_task(health_task_code)
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.post("/health-tasks")
def create_health_task(
    payload: HealthTaskCreateRequest,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.create_task(payload.model_dump())
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.patch("/health-tasks/{health_task_code}")
def update_health_task(
    health_task_code: str,
    payload: HealthTaskUpdateRequest,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.update_task(
        health_task_code, payload.model_dump(exclude_unset=True)
    )
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.post("/health-tasks/{health_task_code}/toggle")
def toggle_health_task(
    health_task_code: str,
    payload: HealthTaskToggleRequest,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.toggle_task(
        health_task_code=health_task_code, enabled=payload.enabled
    )
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.post("/health-tasks/{health_task_code}/check")
def execute_health_check(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.execute_check(health_task_code)
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.get("/health-tasks/{health_task_code}/timeline")
def get_health_task_timeline(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    return success_response(service.get_timeline(health_task_code))


@router.post("/health-tasks/{health_task_code}/repair")
def execute_health_repair(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.execute_repair(health_task_code)
    return success_response(HealthTaskResponse.model_validate(result).model_dump())


@router.delete("/health-tasks/{health_task_code}")
def delete_health_task(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    service.delete_task(health_task_code)
    return success_response(None)


@router.post("/health-tasks/{health_task_code}/clone")
def clone_health_task(
    health_task_code: str,
    service: HealthTaskService = Depends(build_health_task_service),
) -> dict[str, object]:
    result = service.clone_task(health_task_code)
    return success_response(HealthTaskResponse.model_validate(result).model_dump())
