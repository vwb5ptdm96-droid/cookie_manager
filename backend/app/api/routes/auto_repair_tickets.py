from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.config import PROJECT_ROOT, get_settings
from app.core.errors import AppError
from app.core.response import success_response
from app.services.agent_chat_service import AgentChatService
from app.services.auto_repair_ticket_service import AutoRepairTicketService, purge_ticket_artifacts
from app.services.ops_summary_service import build_ops_summary
from app.services.sre_service import SreService

router = APIRouter(tags=["auto-repair-tickets"])


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    ticket_id: int | None = None


class SreConfirmRequest(BaseModel):
    confirmed: bool = False


def build_auto_repair_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> AutoRepairTicketService:
    engine: Engine = session_factory.kw["bind"]
    return AutoRepairTicketService(engine=engine)


def build_chat_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> AgentChatService:
    engine: Engine = session_factory.kw["bind"]
    settings = get_settings()
    return AgentChatService(engine, settings.runtime_root, PROJECT_ROOT)


def build_sre_service(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> SreService:
    engine: Engine = session_factory.kw["bind"]
    settings = get_settings()
    return SreService(engine, settings.runtime_root, PROJECT_ROOT, app_port=settings.app_port)


@router.get("/agent/ops-summary")
def agent_ops_summary(
    session_factory: sessionmaker = Depends(get_session_factory),
) -> dict[str, object]:
    engine: Engine = session_factory.kw["bind"]
    return success_response(build_ops_summary(engine))


@router.get("/agent/status")
def agent_status(service: AutoRepairTicketService = Depends(build_auto_repair_service)) -> dict[str, object]:
    counts = service.status_counts()
    running = int(counts.get("running") or 0)
    pending = int(counts.get("pending") or 0)
    if running:
        headline = f"Agent 处理中 · {running} 单"
        phase = "running"
    elif pending:
        headline = f"Agent 排队 · {pending} 单"
        phase = "pending"
    else:
        headline = "Agent 空闲"
        phase = "idle"
    return success_response({"counts": counts, "headline": headline, "phase": phase})


@router.get("/agent/chat")
def agent_chat_history(
    ticket_id: int | None = Query(default=None),
    chat: AgentChatService = Depends(build_chat_service),
) -> dict[str, object]:
    return success_response({"items": chat.history(ticket_id)})


@router.post("/agent/chat")
def agent_chat(
    payload: AgentChatRequest,
    chat: AgentChatService = Depends(build_chat_service),
) -> dict[str, object]:
    return success_response(chat.ask(payload.message, ticket_id=payload.ticket_id))


@router.get("/auto-repair-tickets")
def list_auto_repair_tickets(
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    items = service.list_tickets(status=status, kind=kind, limit=limit, offset=offset)
    return success_response({"items": items, "counts": service.status_counts()})


@router.delete("/auto-repair-tickets/{ticket_id}")
def delete_auto_repair_ticket(
    ticket_id: int,
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    row = service.delete_ticket(ticket_id)
    purge_ticket_artifacts(get_settings().runtime_root, str(row.get("ticket_code") or ""))
    return success_response({"deleted": row})


@router.post("/auto-repair-tickets/purge-history")
def purge_auto_repair_history(
    payload: SreConfirmRequest,
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    if not payload.confirmed:
        raise AppError("清理历史必须确认", "TICKET_PURGE_REQUIRED", status_code=400)
    deleted = service.delete_closed_tickets()
    runtime_root = get_settings().runtime_root
    for row in deleted:
        purge_ticket_artifacts(runtime_root, str(row.get("ticket_code") or ""))
    return success_response({"deleted": len(deleted)})


@router.get("/auto-repair-tickets/{ticket_id}")
def get_auto_repair_ticket(
    ticket_id: int,
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    row = service.get_ticket(ticket_id)
    if row is None:
        raise AppError("自动排障工单不存在", "AUTO_REPAIR_TICKET_NOT_FOUND", status_code=404)
    from app.core.config import get_settings
    from app.services.agent_event_builder import collect_ticket_diff, collect_ticket_events, collect_ticket_usage
    from app.services.agent_chat_service import load_chat_history

    runtime_root = get_settings().runtime_root
    code = str(row.get("ticket_code") or "")
    row["events"] = collect_ticket_events(runtime_root, row)
    row["diff"] = collect_ticket_diff(runtime_root, code)
    row["usage"] = collect_ticket_usage(runtime_root, code)
    row["chat"] = load_chat_history(runtime_root, code)
    return success_response(row)


@router.get("/auto-repair-tickets/{ticket_id}/events")
def get_auto_repair_ticket_events(
    ticket_id: int,
    service: AutoRepairTicketService = Depends(build_auto_repair_service),
) -> dict[str, object]:
    row = service.get_ticket(ticket_id)
    if row is None:
        raise AppError("自动排障工单不存在", "AUTO_REPAIR_TICKET_NOT_FOUND", status_code=404)
    from app.core.config import get_settings
    from app.services.agent_event_builder import collect_ticket_diff, collect_ticket_events, collect_ticket_usage

    runtime_root = get_settings().runtime_root
    code = str(row.get("ticket_code") or "")
    return success_response(
        {
            "items": collect_ticket_events(runtime_root, row),
            "diff": collect_ticket_diff(runtime_root, code),
            "usage": collect_ticket_usage(runtime_root, code),
        }
    )


@router.get("/agent/sre/explain")
def sre_explain(sre: SreService = Depends(build_sre_service)) -> dict[str, object]:
    return success_response(sre.explain_backend())


@router.post("/agent/sre/env-check")
def sre_env_check(sre: SreService = Depends(build_sre_service)) -> dict[str, object]:
    return success_response(sre.run_env_check())


@router.post("/agent/sre/recycle-stale-runs")
def sre_recycle_stale_runs(
    payload: SreConfirmRequest,
    sre: SreService = Depends(build_sre_service),
) -> dict[str, object]:
    return success_response(sre.recycle_stale_runs(confirmed=payload.confirmed))


@router.post("/agent/sre/restart-backend")
def sre_restart_backend(
    payload: SreConfirmRequest,
    sre: SreService = Depends(build_sre_service),
) -> dict[str, object]:
    return success_response(sre.restart_backend(confirmed=payload.confirmed))


@router.get("/agent/sre/health-probe")
def sre_health_probe(sre: SreService = Depends(build_sre_service)) -> dict[str, object]:
    return success_response(sre.probe_health())
