from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.health_check import HealthCheckConfig
from app.models.profile_registry import ProfileRegistry
from app.models.repair_ticket import ManualRepairTicket
from app.models.script_registry import ScriptRegistry
from app.models.session_task import SessionMaintenanceTask
from app.services.health_check_service import HealthCheckService
from app.services.local_windows_executor import LocalWindowsExecutor
from app.services.profile_service import ProfileService
from app.services.run_log_service import RunLogService


class RepairService:
    def __init__(
        self,
        *,
        engine: Engine,
        runtime_root: Path,
        health_check_executor=None,
    ) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        self.profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
        self.executor = LocalWindowsExecutor()
        self.health_check_service = HealthCheckService(engine=engine, runtime_root=runtime_root)
        self.health_check_executor = health_check_executor or self._default_health_check_executor
        self.log_service = RunLogService(engine=engine)

    def list_tickets(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(select(ManualRepairTicket).order_by(ManualRepairTicket.created_at.desc())).scalars().all()
            return [self._serialize(session, row) for row in rows]

    def open_browser(self, ticket_code: str, *, repaired_by: str | None = None) -> dict[str, object]:
        with Session(self.engine) as session:
            ticket = self._get_ticket(session, ticket_code)
            self._ensure_ticket_status(ticket, allowed={"OPEN", "WAIT_RDP_REPAIR", "FAILED"})
            task = self._get_task(session, ticket.task_code)
            profile_key = ticket.profile_key
            manual_script = self._get_manual_script(session, task.channel)

        self.profile_service.lock(ticket.profile_key, owner=ticket_code)
        artifact_dir = self._build_artifact_dir(ticket.ticket_code)
        try:
            self._run_manual_script(ticket_code=ticket_code, repaired_by=repaired_by, artifact_dir=artifact_dir, script=manual_script)
        except Exception:
            self.profile_service.unlock(ticket.profile_key)
            raise

        with Session(self.engine) as session:
            ticket = self._get_ticket(session, ticket_code)
            ticket.status = "BROWSER_OPENED"
            ticket.repaired_by = repaired_by
            ticket.browser_artifact_dir = str(artifact_dir)
            ticket.browser_opened_at = datetime.now()
            session.commit()
            session.refresh(ticket)
            task = self._get_task(session, ticket.task_code)
            self.log_service.write(
                run_id=f"repair_{ticket.ticket_code}_open",
                run_type="REPAIR",
                task_id=task.id,
                ticket_id=ticket.id,
                status="BROWSER_OPENED",
                title=ticket.ticket_code,
                message="人工修复浏览器已打开",
                log_file_path=str(artifact_dir / "runtime.log"),
            )
            return self._serialize(session, ticket)

    def verify(self, ticket_code: str, *, repaired_by: str | None = None) -> dict[str, object]:
        with Session(self.engine) as session:
            ticket = self._get_ticket(session, ticket_code)
            self._ensure_ticket_status(ticket, allowed={"BROWSER_OPENED", "VERIFYING"})
            task = self._get_task(session, ticket.task_code)
            profile_key = ticket.profile_key
            checks = session.execute(
                select(HealthCheckConfig).where(HealthCheckConfig.trigger_task_id == task.id).order_by(HealthCheckConfig.created_at.asc())
            ).scalars().all()
            check_codes = [check.check_code for check in checks]
            if not checks:
                raise AppError("未找到绑定的健康检测", "REPAIR_CHECK_NOT_FOUND", status_code=404)
            ticket.status = "VERIFYING"
            ticket.repaired_by = repaired_by or ticket.repaired_by
            session.commit()

        self.profile_service.unlock(profile_key)

        results: list[dict[str, object]] = []
        for check_code in check_codes:
            try:
                result = self.health_check_executor(check_code)
            except AppError as exc:
                result = {"status": "FAIL", "message": exc.message, "error_code": exc.code}
            except Exception as exc:  # pragma: no cover - defensive fallback
                result = {"status": "FAIL", "message": str(exc), "error_code": "REPAIR_VERIFY_FAILED"}
            results.append(result)
        all_passed = all(result.get("status") == "PASS" for result in results)

        with Session(self.engine) as session:
            ticket = self._get_ticket(session, ticket_code)
            task = self._get_task(session, ticket.task_code)
            profile = self._get_profile(session, ticket.profile_key)

            if all_passed:
                ticket.status = "CLOSED"
                ticket.closed_at = datetime.now()
                task.status = "VALID"
                task.last_error = None
                profile.status = "READY"
                profile.is_locked = False
                profile.lock_owner = None
            else:
                ticket.status = "FAILED"
                task.status = "RISK"
                profile.status = "RISK"
                profile.is_locked = False
                profile.lock_owner = None

            session.commit()
            session.refresh(ticket)
            self.log_service.write(
                run_id=f"repair_{ticket.ticket_code}_verify",
                run_type="REPAIR",
                task_id=task.id,
                ticket_id=ticket.id,
                status=ticket.status,
                title=ticket.ticket_code,
                message="人工修复复检通过" if all_passed else "人工修复复检失败",
                log_file_path=str(Path(ticket.browser_artifact_dir) / "runtime.log") if ticket.browser_artifact_dir else None,
            )
            return self._serialize(session, ticket)

    def close_ticket(self, ticket_code: str, *, repaired_by: str | None = None) -> dict[str, object]:
        with Session(self.engine) as session:
            ticket = self._get_ticket(session, ticket_code)
            self._ensure_ticket_status(ticket, allowed={"OPEN", "WAIT_RDP_REPAIR", "BROWSER_OPENED", "VERIFYING", "FAILED"})
            task = self._get_task(session, ticket.task_code)
            profile = self._get_profile(session, ticket.profile_key)

            ticket.status = "CLOSED"
            ticket.repaired_by = repaired_by or ticket.repaired_by
            ticket.closed_at = datetime.now()
            task.status = "RISK"
            profile.status = "RISK"
            profile.is_locked = False
            profile.lock_owner = None

            session.commit()
            session.refresh(ticket)
            self.log_service.write(
                run_id=f"repair_{ticket.ticket_code}_close",
                run_type="REPAIR",
                task_id=task.id,
                ticket_id=ticket.id,
                status="CLOSED",
                title=ticket.ticket_code,
                message="人工修复工单已手动关闭，任务保持风险状态",
                log_file_path=str(Path(ticket.browser_artifact_dir) / "runtime.log") if ticket.browser_artifact_dir else None,
            )
            return self._serialize(session, ticket)

    def _run_manual_script(self, *, ticket_code: str, repaired_by: str | None, artifact_dir: Path, script: ScriptRegistry) -> None:
        config = {
            "ticket_code": ticket_code,
            "repaired_by": repaired_by,
            "artifact_dir": str(artifact_dir),
        }
        config_path = artifact_dir / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        script_path = self.runtime_root / Path(*Path(script.script_dir).parts) / script.main_file
        self.executor.execute(
            script_path=script_path,
            artifact_dir=artifact_dir,
            extra_env={
                "TICKET_CODE": ticket_code,
                "REPAIRED_BY": repaired_by or "",
            },
        )

    def _default_health_check_executor(self, check_code: str) -> dict[str, object]:
        return self.health_check_service.execute_check(check_code, allow_trigger_task=False)

    def _get_ticket(self, session: Session, ticket_code: str) -> ManualRepairTicket:
        row = session.execute(select(ManualRepairTicket).where(ManualRepairTicket.ticket_code == ticket_code)).scalar_one_or_none()
        if row is None:
            raise AppError("人工修复工单不存在", "REPAIR_TICKET_NOT_FOUND", status_code=404)
        return row

    def _get_task(self, session: Session, task_code: str) -> SessionMaintenanceTask:
        row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.task_code == task_code)).scalar_one_or_none()
        if row is None:
            raise AppError("关联维护任务不存在", "TASK_NOT_FOUND", status_code=404)
        return row

    def _get_profile(self, session: Session, profile_key: str) -> ProfileRegistry:
        row = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == profile_key)).scalar_one_or_none()
        if row is None:
            raise AppError("Profile 不存在", "PROFILE_NOT_FOUND", status_code=404)
        return row

    def _get_manual_script(self, session: Session, platform: str) -> ScriptRegistry:
        rows = session.execute(
            select(ScriptRegistry).where(
                ScriptRegistry.script_type == "MANUAL",
                ScriptRegistry.enabled.is_(True),
            )
        ).scalars().all()
        for row in rows:
            if row.platform == platform:
                return row
        for row in rows:
            if row.platform == "COMMON":
                return row
        raise AppError("未找到可用的 MANUAL 脚本", "MANUAL_SCRIPT_NOT_FOUND", status_code=404)

    def _build_artifact_dir(self, ticket_code: str) -> Path:
        path = self.runtime_root / "artifacts" / "repairs" / ticket_code / f"run_{uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _ensure_ticket_status(self, ticket: ManualRepairTicket, *, allowed: set[str]) -> None:
        if ticket.status not in allowed:
            raise AppError(
                f"当前工单状态 {ticket.status} 不允许执行该操作",
                "REPAIR_STATUS_INVALID",
                status_code=409,
            )

    def _serialize(self, session: Session, row: ManualRepairTicket) -> dict[str, object]:
        task = self._get_task(session, row.task_code)
        profile = self._get_profile(session, row.profile_key)
        return {
            "ticket_code": row.ticket_code,
            "task_code": row.task_code,
            "task_name": task.task_name,
            "profile_key": row.profile_key,
            "profile_path": str(self.profile_service._resolve_profile_path(profile.relative_path)),
            "risk_type": row.risk_type,
            "risk_message": row.risk_message,
            "status": row.status,
            "repaired_by": row.repaired_by,
            "browser_artifact_dir": row.browser_artifact_dir,
            "browser_opened_at": row.browser_opened_at,
            "closed_at": row.closed_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
