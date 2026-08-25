from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_runtime_root, get_session_factory
from app.core.response import success_response
from app.schemas.repair_ticket import RepairActionRequest, RepairTicketListResponse, RepairTicketResponse
from app.services.repair_service import RepairService


router = APIRouter(tags=["repairs"])


def build_repair_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    runtime_root: Path = Depends(get_runtime_root),
) -> RepairService:
    engine: Engine = session_factory.kw["bind"]
    return RepairService(engine=engine, runtime_root=runtime_root)


@router.get("/repairs")
def list_repairs(service: RepairService = Depends(build_repair_service)) -> dict[str, object]:
    data = RepairTicketListResponse(items=[RepairTicketResponse.model_validate(item) for item in service.list_tickets()])
    return success_response(data.model_dump())


@router.post("/repairs/{ticket_code}/open")
def open_repair_browser(
    ticket_code: str,
    payload: RepairActionRequest,
    service: RepairService = Depends(build_repair_service),
) -> dict[str, object]:
    result = service.open_browser(ticket_code, repaired_by=payload.repaired_by)
    return success_response(RepairTicketResponse.model_validate(result).model_dump())


@router.post("/repairs/{ticket_code}/verify")
def verify_repair(
    ticket_code: str,
    payload: RepairActionRequest,
    service: RepairService = Depends(build_repair_service),
) -> dict[str, object]:
    result = service.verify(ticket_code, repaired_by=payload.repaired_by)
    return success_response(RepairTicketResponse.model_validate(result).model_dump())


@router.post("/repairs/{ticket_code}/close")
def close_repair_ticket(
    ticket_code: str,
    payload: RepairActionRequest,
    service: RepairService = Depends(build_repair_service),
) -> dict[str, object]:
    result = service.close_ticket(ticket_code, repaired_by=payload.repaired_by)
    return success_response(RepairTicketResponse.model_validate(result).model_dump())
