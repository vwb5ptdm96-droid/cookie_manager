from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.script_registry import ScriptListResponse, ScriptMainFileRequest, ScriptProfileRequest, ScriptResponse, ScriptRunConfigRequest, ScriptToggleRequest, ScriptUpdateRequest
from app.services.script_service import ScriptService


router = APIRouter(tags=["scripts"])


def build_script_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> ScriptService:
    engine: Engine = session_factory.kw["bind"]
    return ScriptService(engine=engine, runtime_root=runtime_root)


@router.get("/scripts")
def list_scripts(service: ScriptService = Depends(build_script_service)) -> dict[str, object]:
    data = ScriptListResponse(items=[ScriptResponse.model_validate(item) for item in service.list_scripts()])
    return success_response(data.model_dump())


@router.post("/scripts/upload")
async def upload_script(
    script_name: str = Form(...),
    script_code: str | None = Form(default=None),
    script_type: str = Form(...),
    platform: str = Form(...),
    version: str | None = Form(default=None),
    description: str | None = Form(default=None),
    profile_key: str | None = Form(default=None),
    script_file: UploadFile = File(...),
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    content = await script_file.read()
    result = service.upload(
        script_name=script_name,
        script_code=script_code,
        script_type=script_type,
        platform=platform,
        version=version,
        description=description,
        profile_key=profile_key,
        filename=script_file.filename or "script.py",
        content=content,
    )
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.post("/scripts/{script_code}/toggle")
def toggle_script(
    script_code: str,
    payload: ScriptToggleRequest,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.set_enabled(script_code=script_code, enabled=payload.enabled)
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.patch("/scripts/{script_code}/profile")
def update_script_profile(
    script_code: str,
    payload: ScriptProfileRequest,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.update_profile(script_code=script_code, profile_key=payload.profile_key)
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.patch("/scripts/{script_code}/run-config")
def update_script_run_config(
    script_code: str,
    payload: ScriptRunConfigRequest,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.update_run_config(
        script_code=script_code,
        default_run_mode=payload.default_run_mode,
        default_cdp_port=payload.default_cdp_port,
        supports_pause=payload.supports_pause,
        supports_cancel=payload.supports_cancel,
        default_timeout_seconds=payload.default_timeout_seconds,
    )
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.get("/scripts/{script_code}/files")
def list_script_files(
    script_code: str,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    files = service.list_script_files(script_code=script_code)
    return success_response(files)


@router.patch("/scripts/{script_code}/main-file")
def update_script_main_file(
    script_code: str,
    payload: ScriptMainFileRequest,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.update_main_file(script_code=script_code, main_file=payload.main_file)
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.get("/scripts/cdp-port-status")
def get_cdp_port_status(
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    data = service.check_cdp_ports()
    return success_response(data)


@router.post("/scripts/{script_code}/clone")
def clone_script(
    script_code: str,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.clone_script(script_code=script_code)
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.patch("/scripts/{script_code}/update")
def update_script_meta(
    script_code: str,
    payload: ScriptUpdateRequest,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    result = service.update_script(
        script_code=script_code,
        script_name=payload.script_name,
        script_type=payload.script_type,
        platform=payload.platform,
        description=payload.description,
    )
    return success_response(ScriptResponse.model_validate(result).model_dump())


@router.delete("/scripts/{script_code}")
def delete_script(
    script_code: str,
    service: ScriptService = Depends(build_script_service),
) -> dict[str, object]:
    service.delete_script(script_code=script_code)
    return success_response(None)
