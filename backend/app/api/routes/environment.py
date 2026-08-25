from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.services.environment_service import EnvironmentService


router = APIRouter(tags=["environment"])


def build_environment_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> EnvironmentService:
    engine: Engine = session_factory.kw["bind"]
    return EnvironmentService(engine=engine, runtime_root=runtime_root)


@router.post("/environment/checks/execute")
def execute_environment_checks(service: EnvironmentService = Depends(build_environment_service)) -> dict[str, object]:
    return success_response(service.execute_checks())


@router.get("/environment/checks/latest")
def get_latest_environment_checks(service: EnvironmentService = Depends(build_environment_service)) -> dict[str, object]:
    return success_response(service.get_latest_checks())
