from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.path_utils import resolve_runtime_path
from app.models.health_task import HealthTask
from app.models.script_registry import ScriptRegistry
from app.models.script_run import ScriptRun

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {
    "PENDING",
    "RUNNING",
    "PAUSED",
    "CANCELING",
    "CANCELED",
    "SUCCESS",
    "FAIL",
    "RISK",
}


class ScriptRunService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root

    # ── CRUD ──

    def list_runs(
        self,
        *,
        status: str | None = None,
        health_task_code: str | None = None,
        script_code: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            query = select(ScriptRun).order_by(ScriptRun.created_at.desc())
            if status:
                query = query.where(ScriptRun.status == status)
            if health_task_code:
                query = query.where(ScriptRun.health_task_code == health_task_code)
            if script_code:
                query = query.where(ScriptRun.script_code == script_code)
            rows = session.execute(query.limit(limit)).scalars().all()
        return [self._serialize(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            return self._serialize(row)

    def get_running(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(ScriptRun).where(
                        ScriptRun.status.in_(
                            ["PENDING", "RUNNING", "PAUSED", "CANCELING"]
                        )
                    ).order_by(ScriptRun.created_at.desc())
                )
                .scalars()
                .all()
            )
        return [self._serialize(row) for row in rows]

    # ── 控制 ──

    def pause_run(self, run_id: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            if row.status != "RUNNING":
                raise AppError(
                    f"当前状态为 {row.status}，不允许暂停", "INVALID_STATUS"
                )
            self._write_control(
                row.control_file, {"pause": True, "cancel": False}
            )
            row.status = "PAUSED"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def resume_run(self, run_id: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            if row.status != "PAUSED":
                raise AppError(
                    f"当前状态为 {row.status}，不允许继续", "INVALID_STATUS"
                )
            self._write_control(
                row.control_file, {"pause": False, "cancel": False}
            )
            row.status = "RUNNING"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def cancel_run(self, run_id: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            if row.status not in ("RUNNING", "PAUSED"):
                raise AppError(
                    f"当前状态为 {row.status}，不允许取消", "INVALID_STATUS"
                )

            # 写 control.json
            self._write_control(
                row.control_file, {"pause": False, "cancel": True}
            )
            row.status = "CANCELING"
            session.commit()

            # 杀进程树
            if row.pid:
                self._kill_process_tree(row.pid)

            row.status = "CANCELED"
            row.end_time = __import__("datetime").datetime.now()
            if row.start_time and row.end_time:
                row.duration_ms = int(
                    (row.end_time - row.start_time).total_seconds() * 1000
                )
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    # ── 日志 ──

    def read_log(
        self, run_id: str, offset: int = 0, max_bytes: int = 65536
    ) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            if not row.log_file:
                return {"content": "", "offset": 0, "total_bytes": 0}

            log_path = Path(row.log_file)
            if not log_path.exists():
                return {"content": "", "offset": 0, "total_bytes": 0}

            total = log_path.stat().st_size
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                content = f.read(max_bytes)
            return {
                "content": content,
                "offset": offset + len(content.encode("utf-8")),
                "total_bytes": total,
            }

    def read_result(self, run_id: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, run_id)
            if row.result_json:
                return json.loads(row.result_json)
            return {"status": "UNKNOWN", "message": "无结果数据"}

    # ── 方案A：自动排障自愈挂载入口 ──

    def handle_run_failure(
        self, run_id: str, error_message: str | None = None
    ) -> None:
        """
        当某个 ScriptRun 执行失败（FAIL）时调用：
        自动关联脚本元数据（脚本物理路径、CDP端口、店铺/渠道），创建 RepairTicket 并唤起 Claude Code 排障。
        """
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRun).where(ScriptRun.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                logger.warning(f"[AutoRepair] 未找到 run_id={run_id} 的运行记录，跳过自动排障")
                return

            # 查询关联的脚本信息（获取 main_file, script_dir, default_cdp_port 等）
            script_path = ""
            cdp_port = 9222
            channel = "未知渠道"
            shop_name = "未知店铺"

            if row.script_code:
                reg = session.execute(
                    select(ScriptRegistry).where(ScriptRegistry.script_code == row.script_code)
                ).scalar_one_or_none()
                if reg:
                    absolute_dir = resolve_runtime_path(self.runtime_root, reg.script_dir)
                    script_path = str(absolute_dir / reg.main_file)
                    cdp_port = reg.default_cdp_port or 9222
                    channel = reg.platform or "未知渠道"
                    shop_name = reg.script_name or "未知店铺"

            err_msg = error_message or row.error_message or "脚本执行异常退出 (FAIL)"

            try:
                from app.services.repair_service_extension import RepairServiceAutoExtension
                RepairServiceAutoExtension.handle_script_failure(
                    db=session,
                    script_run_id=row.id,
                    script_path=script_path,
                    channel=channel,
                    shop_name=shop_name,
                    cdp_port=cdp_port,
                    error_message=err_msg
                )
            except Exception as e:
                logger.error(f"[AutoRepair] 触发自动维修失败: {e}", exc_info=True)

    # ── 内部 ──

    def _get_row(self, session: Session, run_id: str) -> ScriptRun:
        row = session.execute(
            select(ScriptRun).where(ScriptRun.run_id == run_id)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("脚本执行实例不存在", "SCRIPT_RUN_NOT_FOUND", status_code=404)
        return row

    def _write_control(
        self, control_file: str | None, data: dict[str, bool]
    ) -> None:
        if not control_file:
            return
        Path(control_file).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def _kill_process_tree(self, pid: int) -> None:
        """Windows 下终止进程树。"""
        import os
        import signal

        try:
            # 先尝试优雅终止
            os.kill(pid, signal.SIGTERM)
        except (OSError, AttributeError):
            pass

        # Windows 强制杀进程树
        import subprocess
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )

    def _serialize(self, row: ScriptRun) -> dict[str, object]:
        with Session(self.engine) as session:
            health_task_name: str | None = None
            if row.health_task_code:
                ht = session.execute(
                    select(HealthTask.health_task_name).where(HealthTask.health_task_code == row.health_task_code)
                ).scalar_one_or_none()
                health_task_name = ht

            script_name: str | None = None
            if row.script_code:
                sn = session.execute(
                    select(ScriptRegistry.script_name).where(ScriptRegistry.script_code == row.script_code)
                ).scalar_one_or_none()
                script_name = sn

        return {
            "id": row.id,
            "run_id": row.run_id,
            "health_task_id": row.health_task_id,
            "health_task_code": row.health_task_code,
            "health_task_name": health_task_name,
            "script_id": row.script_id,
            "script_code": row.script_code,
            "script_name": script_name,
            "directory_id": row.directory_id,
            "directory_key": row.directory_key,
            "run_mode": row.run_mode,
            "script_config": row.script_config,
            "timeout_seconds": row.timeout_seconds,
            "status": row.status,
            "pid": row.pid,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "duration_ms": row.duration_ms,
            "artifact_dir": row.artifact_dir,
            "log_file": row.log_file,
            "result_json": row.result_json,
            "error_message": row.error_message,
            "exit_code": row.exit_code,
            "control_file": row.control_file,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }