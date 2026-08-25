from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.profile_registry import ProfileListResponse, ProfileLockRequest, ProfileResponse, ProfileUpsertRequest
from app.services.profile_service import ProfilePayload, ProfileService


router = APIRouter(tags=["profiles"])


def build_profile_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> ProfileService:
    engine: Engine = session_factory.kw["bind"]
    return ProfileService(engine=engine, runtime_root=runtime_root)


@router.get("/profiles")
def list_profiles(service: ProfileService = Depends(build_profile_service)) -> dict[str, object]:
    data = ProfileListResponse(items=[ProfileResponse.model_validate(item) for item in service.list_profiles()])
    return success_response(data.model_dump())


@router.post("/profiles")
def upsert_profile(
    payload: ProfileUpsertRequest,
    service: ProfileService = Depends(build_profile_service),
) -> dict[str, object]:
    result = service.upsert(ProfilePayload(**payload.model_dump()))
    return success_response(ProfileResponse.model_validate(result).model_dump())


@router.post("/profiles/{profile_key}/lock")
def lock_profile(
    profile_key: str,
    payload: ProfileLockRequest,
    service: ProfileService = Depends(build_profile_service),
) -> dict[str, object]:
    result = service.lock(profile_key, owner=payload.owner)
    return success_response(ProfileResponse.model_validate(result).model_dump())


@router.post("/profiles/{profile_key}/unlock")
def unlock_profile(profile_key: str, service: ProfileService = Depends(build_profile_service)) -> dict[str, object]:
    result = service.unlock(profile_key)
    return success_response(ProfileResponse.model_validate(result).model_dump())


@router.post("/profiles/{profile_key}/verify")
def verify_profile(profile_key: str, service: ProfileService = Depends(build_profile_service)) -> dict[str, object]:
    result = service.verify(profile_key)
    return success_response(ProfileResponse.model_validate(result).model_dump())


@router.patch("/profiles/{profile_key}")
def update_profile(
    profile_key: str,
    payload: ProfileUpsertRequest,
    service: ProfileService = Depends(build_profile_service),
) -> dict[str, object]:
    result = service.update(profile_key, ProfilePayload(**payload.model_dump()))
    return success_response(ProfileResponse.model_validate(result).model_dump())


@router.delete("/profiles/{profile_key}")
def delete_profile(profile_key: str, service: ProfileService = Depends(build_profile_service)) -> dict[str, object]:
    service.delete(profile_key)
    return success_response({"deleted": True})
