from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime_root
from app.core.response import success_response
from app.services.deploy_service import DeployService


router = APIRouter(tags=["deploy"])


def build_deploy_service(runtime_root: Path = Depends(get_runtime_root)) -> DeployService:
    return DeployService(runtime_root=runtime_root)


@router.get("/deploy/config")
def get_deploy_config(service: DeployService = Depends(build_deploy_service)) -> dict[str, object]:
    return success_response(service.get_config())
