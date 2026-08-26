from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.response import success_response
from app.schemas.cookie_sync import (
    CookieSyncMappingCreateRequest,
    CookieSyncMappingListResponse,
    CookieSyncMappingResponse,
    CookieSyncMappingUpdateRequest,
)
from app.services.cookie_sync_mapping_service import CookieSyncMappingService

router = APIRouter(tags=["cookie-sync-mappings"])


def build_cookie_sync_mapping_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> CookieSyncMappingService:
    engine: Engine = session_factory.kw["bind"]
    return CookieSyncMappingService(engine=engine)


@router.get("/cookie-sync-mappings")
def list_cookie_sync_mappings(
    service: CookieSyncMappingService = Depends(build_cookie_sync_mapping_service),
) -> dict[str, object]:
    data = CookieSyncMappingListResponse(
        items=[CookieSyncMappingResponse.model_validate(item) for item in service.list_mappings()]
    )
    return success_response(data.model_dump())


@router.post("/cookie-sync-mappings")
def create_cookie_sync_mapping(
    payload: CookieSyncMappingCreateRequest,
    service: CookieSyncMappingService = Depends(build_cookie_sync_mapping_service),
) -> dict[str, object]:
    result = service.create_mapping(payload.model_dump())
    return success_response(CookieSyncMappingResponse.model_validate(result).model_dump())


@router.patch("/cookie-sync-mappings/{mapping_id}")
def update_cookie_sync_mapping(
    mapping_id: int,
    payload: CookieSyncMappingUpdateRequest,
    service: CookieSyncMappingService = Depends(build_cookie_sync_mapping_service),
) -> dict[str, object]:
    result = service.update_mapping(mapping_id, payload.model_dump(exclude_unset=True))
    return success_response(CookieSyncMappingResponse.model_validate(result).model_dump())


@router.delete("/cookie-sync-mappings/{mapping_id}")
def delete_cookie_sync_mapping(
    mapping_id: int,
    service: CookieSyncMappingService = Depends(build_cookie_sync_mapping_service),
) -> dict[str, object]:
    service.delete_mapping(mapping_id)
    return success_response(None)
