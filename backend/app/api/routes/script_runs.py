from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.script_run import (
    ScriptRunControlRequest,
    ScriptRunListResponse,
    ScriptRunResponse,
)
from app.services.script_run_service import ScriptRunService

router = APIRouter(tags=["script-runs"])


def build_script_run_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> ScriptRunService:
    engine: Engine = session_factory.kw["bind"]
    return ScriptRunService(engine=engine, runtime_root=runtime_root)


@router.get("/script-runs")
def list_script_runs(
    status: str | None = Query(default=None),
    health_task_code: str | None = Query(default=None),
    script_code: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    data = ScriptRunListResponse(
        items=[
            ScriptRunResponse.model_validate(item)
            for item in service.list_runs(
                status=status,
                health_task_code=health_task_code,
                script_code=script_code,
                limit=limit,
            )
        ]
    )
    return success_response(data.model_dump())


@router.get("/script-runs/running")
def list_running_script_runs(
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    data = ScriptRunListResponse(
        items=[
            ScriptRunResponse.model_validate(item)
            for item in service.get_running()
        ]
    )
    return success_response(data.model_dump())


@router.get("/script-runs/{run_id}")
def get_script_run(
    run_id: str,
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.get_run(run_id)
    return success_response(ScriptRunResponse.model_validate(result).model_dump())


@router.get("/script-runs/{run_id}/log")
def read_script_run_log(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    max_bytes: int = Query(default=65536, ge=256, le=1048576),
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.read_log(run_id, offset=offset, max_bytes=max_bytes)
    return success_response(result)


@router.get("/script-runs/{run_id}/result")
def read_script_run_result(
    run_id: str,
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.read_result(run_id)
    return success_response(result)


@router.post("/script-runs/{run_id}/pause")
def pause_script_run(
    run_id: str,
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.pause_run(run_id)
    return success_response(ScriptRunResponse.model_validate(result).model_dump())


@router.post("/script-runs/{run_id}/resume")
def resume_script_run(
    run_id: str,
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.resume_run(run_id)
    return success_response(ScriptRunResponse.model_validate(result).model_dump())


@router.post("/script-runs/{run_id}/cancel")
def cancel_script_run(
    run_id: str,
    service: ScriptRunService = Depends(build_script_run_service),
) -> dict[str, object]:
    result = service.cancel_run(run_id)
    return success_response(ScriptRunResponse.model_validate(result).model_dump())
