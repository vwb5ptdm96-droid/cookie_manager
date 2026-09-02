from __future__ import annotations

import json
from dataclasses import dataclass
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
from app.services.local_windows_executor import LocalWindowsExecutor
from app.services.profile_service import ProfileService
from app.services.run_log_service import RunLogService


@dataclass(frozen=True)
class SessionTaskPayload:
    task_name: str
    channel: str
    mobile_phone: str
    account_alias: str | None
    related_dns: list[str]
    script_code: str
    profile_key: str
    schedule_type: str = "MANUAL"
    schedule_value: str | None = None
    script_config: dict[str, object] | None = None
    notes: str | None = None


class SessionTaskService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        self.profile_service = ProfileService(engine=engine, runtime_root=runtime_root)
        self.log_service = RunLogService(engine=engine)
        self.executor = LocalWindowsExecutor()

    def list_tasks(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(select(SessionMaintenanceTask).order_by(SessionMaintenanceTask.created_at.desc())).scalars().all()
            return [self._serialize(session, row) for row in rows]

    def create_task(self, payload: SessionTaskPayload) -> dict[str, object]:
        if not payload.related_dns:
            raise AppError("related_dns 至少需要一个 DNS", "INVALID_TASK_PAYLOAD")

        with Session(self.engine) as session:
            script = self._get_script(session, payload.script_code)
            profile = self._get_profile(session, payload.profile_key)
            self._validate_script(script)
            self._validate_profile(profile)

            row = SessionMaintenanceTask(
                task_code=self._build_task_code(),
                task_name=payload.task_name,
                channel=payload.channel,
                mobile_phone=payload.mobile_phone,
                account_alias=payload.account_alias,
                related_dns=json.dumps(payload.related_dns, ensure_ascii=False),
                script_code=payload.script_code,
                profile_key=payload.profile_key,
                schedule_type=payload.schedule_type,
                schedule_value=payload.schedule_value,
                script_config=json.dumps(payload.script_config or {}, ensure_ascii=False),
                status="INIT",
                enabled=True,
                notes=payload.notes,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(session, row)

    def update_task(self, task_code: str, payload: SessionTaskPayload) -> dict[str, object]:
        if not payload.related_dns:
            raise AppError("related_dns 至少需要一个 DNS", "INVALID_TASK_PAYLOAD")

        with Session(self.engine) as session:
            task = self._get_task(session, task_code)
            script = self._get_script(session, payload.script_code)
            profile = self._get_profile(session, payload.profile_key)
            self._validate_script(script)
            self._validate_profile(profile)

            task.task_name = payload.task_name
            task.channel = payload.channel
            task.mobile_phone = payload.mobile_phone
            task.account_alias = payload.account_alias
            task.related_dns = json.dumps(payload.related_dns, ensure_ascii=False)
            task.script_code = payload.script_code
            task.profile_key = payload.profile_key
            task.schedule_type = payload.schedule_type
            task.schedule_value = payload.schedule_value
            task.script_config = json.dumps(payload.script_config or {}, ensure_ascii=False)
            task.notes = payload.notes
            if task.enabled and task.status == "DISABLED":
                task.status = "INIT"

            session.commit()
            session.refresh(task)
            return self._serialize(session, task)

    def toggle_task(self, task_code: str, enabled: bool) -> dict[str, object]:
        with Session(self.engine) as session:
            task = self._get_task(session, task_code)
            task.enabled = enabled
            if not enabled:
                task.status = "DISABLED"
            elif task.status == "DISABLED":
                task.status = "INIT"
            session.commit()
            session.refresh(task)
            return self._serialize(session, task)

    def execute_task(self, task_code: str) -> dict[str, object]:
        run_id = self._build_run_id()
        with Session(self.engine) as session:
            task = self._get_task(session, task_code)
            if not task.enabled:
                raise AppError("任务已停用，不能执行", "TASK_DISABLED", status_code=409)
            script = self._get_script(session, task.script_code)
            effective_profile_key = script.profile_key or task.profile_key
            profile = self._get_profile(session, effective_profile_key)
            self._validate_script(script)
            self._validate_profile(profile)

        self.profile_service.lock(effective_profile_key, owner=run_id)
        artifact_dir = self._build_artifact_dir(task_code, run_id)

        try:
            payload = self._run_task(task_code=task_code, run_id=run_id, artifact_dir=artifact_dir)
        except Exception as exc:
            self.profile_service.unlock(effective_profile_key)
            raise exc

        return payload

    def _run_task(self, *, task_code: str, run_id: str, artifact_dir: Path) -> dict[str, object]:
        with Session(self.engine) as session:
            task = self._get_task(session, task_code)
            script = self._get_script(session, task.script_code)
            effective_profile_key = script.profile_key or task.profile_key
            profile = self._get_profile(session, effective_profile_key)

            config = {
                "run_id": run_id,
                "task_code": task.task_code,
                "task_name": task.task_name,
                "channel": task.channel,
                "mobile_phone": task.mobile_phone,
                "account_alias": task.account_alias,
                "related_dns": json.loads(task.related_dns),
                "script_config": json.loads(task.script_config or "{}"),
                "artifact_dir": str(artifact_dir),
                "profile": {
                    "profile_key": profile.profile_key,
                    "relative_path": profile.relative_path,
                    "absolute_path": self._profile_absolute_path(profile),
                },
            }
            config_path = artifact_dir / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

            script_path = self.runtime_root / Path(*Path(script.script_dir).parts) / script.main_file
            script_cfg = json.loads(task.script_config or "{}")
            result = self.executor.execute(
                script_path=script_path,
                artifact_dir=artifact_dir,
                extra_env={
                    "EXPECTED_STATUS": str(script_cfg.get("expected_status", "SUCCESS")),
                    "EXPECTED_MESSAGE": str(script_cfg.get("message", "task finished")),
                    "CHROME_USER_DATA_DIR": self._profile_absolute_path(profile),
                },
            )
            normalized_status = self._normalize_status(str(result.get("status", "FAIL")))
            message = str(result.get("message", "task finished"))

            task.last_run_id = run_id
            task.last_run_status = normalized_status
            task.last_artifact_dir = str(artifact_dir)
            task.last_run_at = datetime.now()
            task.last_error = None if normalized_status == "SUCCESS" else message

            if normalized_status == "SUCCESS":
                task.status = "VALID"
                self.profile_service.unlock(effective_profile_key)
            elif normalized_status == "RISK":
                task.status = "RISK"
                self.profile_service.mark_risk(effective_profile_key)
                self.profile_service.unlock(effective_profile_key)
                session.add(
                    ManualRepairTicket(
                        ticket_code=self._build_ticket_code(),
                        task_code=task.task_code,
                        profile_key=effective_profile_key,
                        risk_type="RISK",
                        status="OPEN",
                        risk_message=message,
                    )
                )
            else:
                task.status = "EXPIRED"
                self.profile_service.unlock(effective_profile_key)

            session.commit()
            session.refresh(task)

        self.log_service.write(
            run_id=run_id,
            run_type="TASK",
            task_id=task.id,
            status=normalized_status,
            title=task_code,
            message=message,
            log_file_path=str(artifact_dir / "runtime.log"),
        )

        with Session(self.engine) as session:
            task = self._get_task(session, task_code)
            return {
                **self._serialize(session, task),
                "artifact_dir": str(artifact_dir),
            }

    def _get_task(self, session: Session, task_code: str) -> SessionMaintenanceTask:
        row = session.execute(
            select(SessionMaintenanceTask).where(SessionMaintenanceTask.task_code == task_code)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("维护任务不存在", "TASK_NOT_FOUND", status_code=404)
        return row

    def _get_script(self, session: Session, script_code: str) -> ScriptRegistry:
        row = session.execute(select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)).scalar_one_or_none()
        if row is None:
            raise AppError("维护脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
        return row

    def _get_profile(self, session: Session, profile_key: str) -> ProfileRegistry:
        row = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == profile_key)).scalar_one_or_none()
        if row is None:
            raise AppError("Profile 不存在", "PROFILE_NOT_FOUND", status_code=404)
        return row

    def _profile_absolute_path(self, profile: ProfileRegistry) -> str:
        p = Path(profile.relative_path)
        return str(p) if p.is_absolute() else str(self.runtime_root / Path(*Path(profile.relative_path).parts))

    def _validate_script(self, script: ScriptRegistry) -> None:
        if script.script_type != "MAINTAIN" or not script.enabled:
            raise AppError("仅允许绑定已启用的 MAINTAIN 脚本", "INVALID_TASK_SCRIPT")

    def _validate_profile(self, profile: ProfileRegistry) -> None:
        if profile.status in {"CORRUPTED", "MISSING"}:
            raise AppError("Profile 当前不可用于维护任务", "INVALID_TASK_PROFILE")

    def _serialize(self, session: Session, row: SessionMaintenanceTask) -> dict[str, object]:
        script = session.execute(select(ScriptRegistry).where(ScriptRegistry.script_code == row.script_code)).scalar_one_or_none()
        profile = session.execute(select(ProfileRegistry).where(ProfileRegistry.profile_key == row.profile_key)).scalar_one_or_none()
        check_codes = session.execute(
            select(HealthCheckConfig.check_code).where(HealthCheckConfig.trigger_task_id == row.id)
        ).scalars().all()
        return {
            "id": row.id,
            "task_code": row.task_code,
            "task_name": row.task_name,
            "channel": row.channel,
            "mobile_phone": row.mobile_phone,
            "account_alias": row.account_alias,
            "related_dns": json.loads(row.related_dns),
            "script_code": row.script_code,
            "script_name": script.script_name if script else None,
            "script_type": script.script_type if script else None,
            "platform": script.platform if script else None,
            "profile_key": row.profile_key,
            "profile_relative_path": profile.relative_path if profile else None,
            "profile_absolute_path": self._profile_absolute_path(profile) if profile else None,
            "schedule_type": row.schedule_type,
            "schedule_value": row.schedule_value,
            "script_config": json.loads(row.script_config or "{}"),
            "script_dir": script.script_dir if script else None,
            "script_main_file": script.main_file if script else None,
            "health_check_codes": check_codes,
            "status": row.status,
            "enabled": row.enabled,
            "last_run_status": row.last_run_status,
            "last_run_id": row.last_run_id,
            "last_error": row.last_error,
            "last_artifact_dir": row.last_artifact_dir,
            "last_run_at": row.last_run_at,
            "updated_at": row.updated_at,
        }

    def _build_task_code(self) -> str:
        return f"task_{uuid4().hex[:10]}"

    def _build_run_id(self) -> str:
        return f"run_{uuid4().hex[:12]}"

    def _build_ticket_code(self) -> str:
        return f"ticket_{uuid4().hex[:10]}"

    def _build_artifact_dir(self, task_code: str, run_id: str) -> Path:
        artifact_dir = self.runtime_root / "artifacts" / task_code / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _normalize_status(self, status: str) -> str:
        normalized = status.upper()
        if normalized in {"SUCCESS", "FAIL", "RISK"}:
            return normalized
        return "FAIL"
