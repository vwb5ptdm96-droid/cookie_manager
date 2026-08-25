from __future__ import annotations

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models.health_check import HealthCheckConfig
from app.models.profile_registry import ProfileRegistry
from app.models.repair_ticket import ManualRepairTicket
from app.models.run_log import TaskRunLog
from app.models.session_task import SessionMaintenanceTask


class DashboardService:
    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine

    def get_dashboard(self) -> dict[str, object]:
        with Session(self.engine) as session:
            tasks = session.execute(select(func.count(SessionMaintenanceTask.id))).scalar_one()
            profiles = session.execute(select(func.count(ProfileRegistry.id))).scalar_one()
            checks = session.execute(select(func.count(HealthCheckConfig.id))).scalar_one()
            pending_repairs = session.execute(
                select(func.count(ManualRepairTicket.id)).where(ManualRepairTicket.status != "CLOSED")
            ).scalar_one()

            recent_logs = session.execute(
                select(TaskRunLog).order_by(TaskRunLog.created_at.desc(), TaskRunLog.id.desc()).limit(5)
            ).scalars().all()
            recent_checks = session.execute(
                select(HealthCheckConfig).order_by(HealthCheckConfig.updated_at.desc(), HealthCheckConfig.id.desc()).limit(5)
            ).scalars().all()

        return {
            "stats": {
                "tasks": int(tasks or 0),
                "profiles": int(profiles or 0),
                "checks": int(checks or 0),
                "pending_repairs": int(pending_repairs or 0),
            },
            "recent_logs": [
                {
                    "run_id": row.run_id,
                    "run_type": row.run_type,
                    "status": row.status,
                    "title": row.title,
                    "message": row.message,
                    "created_at": row.created_at,
                }
                for row in recent_logs
            ],
            "recent_checks": [
                {
                    "check_code": row.check_code,
                    "check_name": row.check_name,
                    "status": row.status,
                    "last_result_message": row.last_result_message,
                    "last_checked_at": row.last_checked_at,
                    "updated_at": row.updated_at,
                }
                for row in recent_checks
            ],
        }
