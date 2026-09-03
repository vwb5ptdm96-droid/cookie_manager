from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.errors import AppError
from app.core.response import success_response
from app.services.auto_repair_ticket_service import AutoRepairTicketService

router = APIRouter(tags=["auto-repair-tickets"])


def build_auto_repair_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> AutoRepairTicketService:
    engine: Engine = session_factory.kw["bind"]
    return AutoRepairTicketService(engine=engine)


@router.get("/auto-repair-tickets")
def list_auto_repair_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    items = service.list_tickets(status=status, limit=limit, offset=offset)
    return success_response({"items": items})


@router.get("/auto-repair-tickets/{ticket_id}")
def get_auto_repair_ticket(
    ticket_id: int,
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    row = service.get_ticket(ticket_id)
    if row is None:
        raise AppError("自动排障工单不存在", "AUTO_REPAIR_TICKET_NOT_FOUND", status_code=404)
    return success_response(row)
