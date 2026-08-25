from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.health_check import (
    HealthCheckCreateRequest,
    HealthCheckListResponse,
    HealthCheckResponse,
    HealthCheckToggleRequest,
)
from app.services.health_check_service import HealthCheckPayload, HealthCheckService


router = APIRouter(tags=["health-checks"])


def build_health_check_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> HealthCheckService:
    engine: Engine = session_factory.kw["bind"]
    return HealthCheckService(engine=engine, runtime_root=runtime_root)


@router.get("/health-checks")
def list_health_checks(service: HealthCheckService = Depends(build_health_check_service)) -> dict[str, object]:
    data = HealthCheckListResponse(items=[HealthCheckResponse.model_validate(item) for item in service.list_checks()])
    return success_response(data.model_dump())


@router.post("/health-checks")
def create_health_check(
    payload: HealthCheckCreateRequest,
    service: HealthCheckService = Depends(build_health_check_service),
) -> dict[str, object]:
    result = service.create_check(HealthCheckPayload(**payload.model_dump()))
    return success_response(HealthCheckResponse.model_validate(result).model_dump())


@router.put("/health-checks/{check_code}")
def update_health_check(
    check_code: str,
    payload: HealthCheckCreateRequest,
    service: HealthCheckService = Depends(build_health_check_service),
) -> dict[str, object]:
    result = service.update_check(check_code, HealthCheckPayload(**payload.model_dump()))
    return success_response(HealthCheckResponse.model_validate(result).model_dump())


@router.post("/health-checks/{check_code}/execute")
def execute_health_check(check_code: str, service: HealthCheckService = Depends(build_health_check_service)) -> dict[str, object]:
    result = service.execute_check(check_code)
    return success_response(HealthCheckResponse.model_validate(result).model_dump())


@router.post("/health-checks/execute-all")
def execute_all_health_checks(service: HealthCheckService = Depends(build_health_check_service)) -> dict[str, object]:
    result = [HealthCheckResponse.model_validate(item).model_dump() for item in service.execute_all_checks()]
    return success_response({"items": result})


@router.post("/health-checks/{check_code}/toggle")
def toggle_health_check(
    check_code: str,
    payload: HealthCheckToggleRequest,
    service: HealthCheckService = Depends(build_health_check_service),
) -> dict[str, object]:
    result = service.toggle_check(check_code, enabled=payload.enabled)
    return success_response(HealthCheckResponse.model_validate(result).model_dump())
