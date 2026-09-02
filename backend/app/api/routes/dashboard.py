from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_session_factory
from app.core.response import success_response
from app.services.dashboard_service import DashboardService


router = APIRouter(tags=["dashboard"])


def build_dashboard_service(session_factory: sessionmaker = Depends(get_session_factory)) -> DashboardService:
    engine: Engine = session_factory.kw["bind"]
    return DashboardService(engine=engine)


@router.get("/dashboard")
def get_dashboard(service: DashboardService = Depends(build_dashboard_service)) -> dict[str, object]:
    return success_response(service.get_dashboard())
