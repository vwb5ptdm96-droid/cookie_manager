from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# 全局修复锁：保证所有 execute_repair 串行执行
_repair_lock = threading.Lock()

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """返回当前北京时间（naive datetime，不含时区信息，可直接写入 DB）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.builtin_scripts.health_request import perform_health_request
from app.core.config import create_mysql_engine, get_settings
from app.core.errors import AppError
from app.core.path_utils import PathSecurityError, resolve_runtime_path
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.script_registry import ScriptRegistry
from app.models.script_run import ScriptRun
from app.services.chrome_utils import kill_chrome_for_profile, kill_chrome_on_port
from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService
from app.services.local_windows_executor import LocalWindowsExecutor
from app.services.notification_service import send_feishu_notification
from app.services.run_log_service import RunLogService
from app.services.agent_repair_dispatcher import trigger_auto_repair


ALLOWED_CHANNELS = {"KUAISHOU", "TAOBAO", "TMALL", "ALIMAMA", "JD", "PDD"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ALLOWED_RUN_MODES = {"HEADLESS", "HEADED"}
RUNNING_STATUSES = {"PENDING", "RUNNING", "PAUSED", "CANCELING"}
# 僵死执行实例宽限期：超过 (timeout_seconds + grace) 仍非终态才回收，防误杀刚启动的实例
STALE_RUN_GRACE_SECONDS = 120


def kill_process_tree(pid: int) -> None:
    """Windows 下尽力强杀进程树（含子进程）。进程已不存在/失败一律静默。"""
    if not pid:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        pass


class HealthTaskService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        self.executor = LocalWindowsExecutor()
        cookie_engine = create_mysql_engine() or engine
        self.legacy_cookie_service = LegacyCookieService(engine=cookie_engine)
        self.log_service = RunLogService(engine=engine)

    # ── CRUD ──

    def list_tasks(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(HealthTask).order_by(HealthTask.created_at.desc())
                )
                .scalars()
                .all()
            )
        return [self._serialize(row) for row in rows]

    def get_task(self, health_task_code: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)
            return self._serialize(row)

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        self._validate_payload(payload, is_create=True)
        health_task_code = f"ht_{uuid4().hex[:10]}"

        with Session(self.engine) as session:
            row = HealthTask(
                health_task_code=health_task_code,
                health_task_name=payload["health_task_name"].strip(),
                cookie_table=payload.get("cookie_table", "ods_cookie_playwright"),
                channel=payload["channel"],
                shop_name=payload.get("shop_name"),
                mobile_phone=payload.get("mobile_phone"),
                dns=payload.get("dns"),
                check_url=payload["check_url"],
                http_method=payload.get("http_method", "GET"),
                http_headers=payload.get("http_headers"),
                http_body=payload.get("http_body"),
                success_rule=payload.get("success_rule"),
                failure_rule=payload.get("failure_rule"),
                cron_expression=payload.get("cron_expression"),
                check_timeout_seconds=payload.get("check_timeout_seconds", 30),
                retry_count=payload.get("retry_count", 0),
                auto_repair_enabled=payload.get("auto_repair_enabled", False),
                repair_cron_expression=payload.get("repair_cron_expression"),
                repair_script_id=payload.get("repair_script_id"),
                repair_directory_id=payload.get("repair_directory_id"),
                repair_run_mode=payload.get("repair_run_mode"),
                repair_script_config=payload.get("repair_script_config"),
                repair_timeout_seconds=payload.get("repair_timeout_seconds", 600),
                status="PENDING",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def update_task(
        self, health_task_code: str, payload: dict[str, object]
    ) -> dict[str, object]:
        self._validate_payload(payload, is_create=False)

        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)
            simple_fields = {
                "health_task_name": str,
                "cookie_table": str,
                "channel": str,
                "shop_name": (str, type(None)),
                "mobile_phone": (str, type(None)),
                "dns": (str, type(None)),
                "check_url": str,
                "http_method": str,
                "http_headers": (str, type(None)),
                "http_body": (str, type(None)),
                "success_rule": (str, type(None)),
                "failure_rule": (str, type(None)),
                "cron_expression": (str, type(None)),
                "check_timeout_seconds": int,
                "retry_count": int,
                "auto_repair_enabled": bool,
                "repair_cron_expression": (str, type(None)),
                "repair_script_id": (int, type(None)),
                "repair_directory_id": (int, type(None)),
                "repair_run_mode": (str, type(None)),
                "repair_script_config": (str, type(None)),
                "repair_timeout_seconds": int,
            }
            for field, expected_types in simple_fields.items():
                if field in payload:
                    value = payload[field]
                    if value is not None and not isinstance(value, expected_types):
                        raise AppError(f"{field} 类型不正确", "INVALID_PAYLOAD")
                    setattr(row, field, value)

            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def toggle_task(
        self, health_task_code: str, enabled: bool
    ) -> dict[str, object]:
        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)
            row.enabled = enabled
            if not enabled:
                row.status = "DISABLED"
            elif row.status == "DISABLED":
                row.status = "PENDING"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def clone_task(self, health_task_code: str) -> dict[str, object]:
        with Session(self.engine) as session:
            source = self._get_row(session, health_task_code)
            new_code = f"ht_{uuid4().hex[:10]}"

            row = HealthTask(
                health_task_code=new_code,
                health_task_name=f"{source.health_task_name} (副本)",
                cookie_table=source.cookie_table,
                channel=source.channel,
                shop_name=source.shop_name,
                mobile_phone=source.mobile_phone,
                dns=source.dns,
                check_url=source.check_url,
                http_method=source.http_method,
                http_headers=source.http_headers,
                http_body=source.http_body,
                success_rule=source.success_rule,
                failure_rule=source.failure_rule,
                cron_expression=source.cron_expression,
                check_timeout_seconds=source.check_timeout_seconds,
                retry_count=source.retry_count,
                auto_repair_enabled=source.auto_repair_enabled,
                repair_cron_expression=source.repair_cron_expression,
                repair_script_id=source.repair_script_id,
                repair_directory_id=source.repair_directory_id,
                repair_run_mode=source.repair_run_mode,
                repair_script_config=source.repair_script_config,
                repair_timeout_seconds=source.repair_timeout_seconds,
                status="PENDING",
                enabled=True,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    # ── 执行 ──

    def execute_check(self, health_task_code: str) -> dict[str, object]:
        run_id = f"check_{uuid4().hex[:12]}"
        steps: list[str] = []

        def add_step(msg: str) -> None:
            ts = beijing_now().strftime("%H:%M:%S")
            steps.append(f"[{ts}] {msg}")

        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)
            if not row.enabled:
                raise AppError("该健康检测任务已停用", "TASK_DISABLED")

            add_step(f"开始检测: {row.health_task_name}")
            add_step(f"目标: {row.http_method} {row.check_url}")

            cookie_headers: dict[str, str] = {}
            try:
                legacy_record = self.legacy_cookie_service.get_by_lookup(
                    LegacyCookieLookup(
                        channel=row.channel,
                        shop_name=row.shop_name or "",
                        mobile_phone=row.mobile_phone or "",
                        dns=row.dns or "",
                    ),
                    table_name=row.cookie_table,
                )
                if legacy_record is not None:
                    add_step(f"✅ 数据库查询成功: 在 {row.cookie_table} 中找到 cookie 记录")
                    cookie_json = legacy_record.get("cookie")
                    if cookie_json:
                        try:
                            parsed = json.loads(cookie_json) if isinstance(cookie_json, str) else cookie_json
                            if isinstance(parsed, list):
                                cookie_parts = []
                                for c in parsed:
                                    if isinstance(c, dict) and "name" in c and "value" in c:
                                        cookie_parts.append(f"{c['name']}={c['value']}")
                                if cookie_parts:
                                    cookie_headers["Cookie"] = "; ".join(cookie_parts)
                            elif isinstance(parsed, dict):
                                cookie_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in parsed.items())
                        except json.JSONDecodeError:
                            pass
                    if "Cookie" not in cookie_headers:
                        str_cookie = legacy_record.get("str_cookie")
                        if isinstance(str_cookie, str) and str_cookie.strip():
                            cookie_headers["Cookie"] = str_cookie.strip()
                else:
                    add_step(f"⚠️ 数据库查询完成: 在 {row.cookie_table} 中未找到匹配的 cookie 记录")
            except SQLAlchemyError as exc:
                add_step(f"⚠️ cookie 表查询失败 ({row.cookie_table}): {exc}")
            except Exception as exc:
                add_step(f"⚠️ cookie 查询异常: {exc}")

            request_headers: dict[str, str] = dict(cookie_headers)
            if row.http_headers:
                try:
                    extra = json.loads(row.http_headers)
                    if isinstance(extra, dict):
                        request_headers.update({str(k): str(v) for k, v in extra.items()})
                except json.JSONDecodeError:
                    pass

            request_body = None
            if row.http_body:
                try:
                    request_body = json.loads(row.http_body)
                except json.JSONDecodeError:
                    request_body = row.http_body

            response_body_preview = ""
            try:
                response = perform_health_request(
                    method=row.http_method,
                    url=row.check_url,
                    headers=request_headers,
                    body=request_body,
                )
                response_status = int(response.get("status_code", 0))
                response_body = response.get("body")

                body_str = (
                    json.dumps(response_body, ensure_ascii=False, indent=2)
                    if isinstance(response_body, (dict, list))
                    else str(response_body)
                )
                masked_body = self._mask_sensitive(body_str)
                response_body_preview = masked_body[:50]
                add_step(f"✅ HTTP 请求完成: 状态码 {response_status}")
                add_step(f"响应内容:\n{masked_body[:2000]}")

                failure_hit = self._match_rule(row.failure_rule, response_status, response_body)
                success_rule_exists = bool(row.success_rule)
                success_hit = self._match_rule(row.success_rule, response_status, response_body)

                if failure_hit:
                    row.status = "FAIL"
                    row.last_run_status = "FAIL"
                    row.last_result_message = f"检测失败: 命中失败规则 (状态码 {response_status})"
                    add_step(f"❌ 检测失败: 命中失败规则")
                elif success_hit:
                    row.status = "PASS"
                    row.last_run_status = "SUCCESS"
                    row.last_result_message = f"检测通过: 命中成功规则 (状态码 {response_status})"
                    add_step(f"✅ 检测通过: 命中成功规则")
                elif success_rule_exists:
                    row.status = "FAIL"
                    row.last_run_status = "FAIL"
                    row.last_result_message = f"检测失败: 未命中成功规则 (状态码 {response_status})"
                    add_step(f"❌ 检测失败: 未命中成功规则")
                else:
                    row.status = "PASS"
                    row.last_run_status = "SUCCESS"
                    row.last_result_message = f"检测通过: 状态码 {response_status}"
                    add_step(f"✅ 检测通过: 状态码 {response_status}")

            except AppError as exc:
                row.status = "FAIL"
                row.last_run_status = "FAIL"
                row.last_result_message = f"检测请求失败: {exc.message}"
                add_step(f"❌ HTTP 请求失败: {exc.message}")
            except Exception as exc:
                row.status = "FAIL"
                row.last_run_status = "FAIL"
                row.last_result_message = f"检测异常: {exc}"
                add_step(f"❌ 检测异常: {exc}")

            row.last_checked_at = beijing_now()
            session.commit()
            session.refresh(row)

        if row.status == "FAIL":
            try:
                send_feishu_notification(
                    title=f"健康检测失败: {row.health_task_name or health_task_code}",
                    message=row.last_result_message or "检测失败",
                    fields={
                        "检测编码": health_task_code,
                        "检测 URL": row.check_url or "",
                        "请求方法": row.http_method or "",
                        "结果信息": row.last_result_message or "",
                        "响应体预览": response_body_preview,
                    },
                )
            except Exception:
                logger.exception("发送飞书通知异常")

            if row.auto_repair_enabled and row.repair_script_id:
                try:
                    logger.info("检测失败，自动触发修复: %s", health_task_code)
                    self.execute_repair(health_task_code)
                except Exception as exc:
                    logger.exception("自动修复执行异常 [%s]: %s", health_task_code, exc)

        detail_message = "\n".join(steps)
        self.log_service.write(
            run_id=run_id,
            run_type="CHECK",
            task_id=row.id,
            status=row.last_run_status or "FAIL",
            title=row.health_task_name,
            message=detail_message,
        )

        result = self._serialize(row)
        result["check_detail"] = detail_message
        return result

    def _safe_kill_chrome(self, profile_path: Path, cdp_port: int, run_id: str) -> None:
        """尽力清理 profile 目录与端口的 Chrome 进程；失败只告警不中断。"""
        try:
            kill_chrome_for_profile(profile_path)
            kill_chrome_on_port(cdp_port)
        except Exception:
            logger.exception("清理 Chrome 异常 run_id=%s", run_id)

    def execute_repair(self, health_task_code: str) -> dict[str, object]:
        with _repair_lock:
            return self._do_execute_repair(health_task_code, force=False)

    def execute_scheduled_repair(self, health_task_code: str) -> dict[str, object]:
        with _repair_lock:
            return self._do_execute_repair(health_task_code, force=True)

    def _do_execute_repair(self, health_task_code: str, force: bool = False) -> dict[str, object]:
        row = self._get_row_internal(health_task_code)

        if not row.enabled:
            raise AppError("该健康检测任务已停用", "TASK_DISABLED")
        if not force and not row.auto_repair_enabled:
            raise AppError("该任务未启用自动修复", "REPAIR_NOT_CONFIGURED")
        if not row.repair_script_id:
            raise AppError("未配置修复脚本", "REPAIR_NOT_CONFIGURED")

        script = self._get_script(row.repair_script_id)
        script_profile_key = script.get("profile_key")
        if script_profile_key:
            profile_by_key = self._get_profile_by_key(script_profile_key)
            effective_directory_id = profile_by_key["id"]
        elif row.repair_directory_id:
            effective_directory_id = row.repair_directory_id
        else:
            raise AppError(
                "未配置启动目录，请在脚本库关联目录或配置修复目录",
                "REPAIR_NOT_CONFIGURED",
            )

        with Session(self.engine) as session:
            existing = (
                session.execute(
                    select(ScriptRun).where(
                        ScriptRun.script_id == row.repair_script_id,
                        ScriptRun.directory_id == effective_directory_id,
                        ScriptRun.status.in_(RUNNING_STATUSES),
                    )
                )
                .scalars()
                .all()
            )
            if existing:
                reclaimed_any = False
                now_dedup = beijing_now()
                for e in list(existing):
                    if self._reclaim_one(session, e, now_dedup):
                        reclaimed_any = True
                if reclaimed_any:
                    session.commit()
                    existing = (
                        session.execute(
                            select(ScriptRun).where(
                                ScriptRun.script_id == row.repair_script_id,
                                ScriptRun.directory_id == effective_directory_id,
                                ScriptRun.status.in_(RUNNING_STATUSES),
                            )
                        )
                        .scalars()
                        .all()
                    )
                if existing:
                    run_ids = ", ".join(e.run_id for e in existing)
                    raise AppError(
                        f"相同脚本+目录的执行实例已存在（{run_ids}），跳过执行",
                        "DUPLICATE_RUN",
                    )

        profile = self._get_profile(effective_directory_id)
        profile_absolute_path = self._resolve_profile_path(profile["relative_path"])
        script_absolute_dir = resolve_runtime_path(self.runtime_root, script["script_dir"])
        script_path = script_absolute_dir / script["main_file"]

        run_mode = row.repair_run_mode or script["default_run_mode"] or "HEADLESS"

        run_id = f"run_{uuid4().hex[:12]}"
        artifact_dir = self.runtime_root / "artifacts" / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        control_file = str(artifact_dir / "control.json")

        config = {
            "run_id": run_id,
            "health_task": {
                "id": row.id,
                "code": row.health_task_code,
                "name": row.health_task_name,
                "channel": row.channel,
                "shop_name": row.shop_name,
                "mobile_phone": row.mobile_phone,
                "dns": row.dns,
            },
            "script": {
                "script_id": script["id"],
                "script_code": script["script_code"],
                "script_dir": str(script_absolute_dir),
                "main_file": script["main_file"],
            },
            "browser_directory": {
                "directory_id": profile["id"],
                "directory_key": profile["profile_key"],
                "directory_path": str(profile_absolute_path),
            },
            "run_mode": run_mode,
            "control_file": control_file,
            "artifact_dir": str(artifact_dir),
            "script_config": (
                json.loads(row.repair_script_config) if row.repair_script_config else {}
            ),
        }
        (artifact_dir / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with Session(self.engine) as session:
            sr = ScriptRun(
                run_id=run_id,
                health_task_id=row.id,
                health_task_code=row.health_task_code,
                script_id=script["id"],
                script_code=script["script_code"],
                directory_id=profile["id"],
                directory_key=profile["profile_key"],
                run_mode=run_mode,
                script_config=row.repair_script_config,
                timeout_seconds=row.repair_timeout_seconds,
                status="PENDING",
                artifact_dir=str(artifact_dir),
                control_file=control_file,
            )
            session.add(sr)

            profile_row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == effective_directory_id)
            ).scalar_one()
            if profile_row.is_locked:
                raise AppError("目录已被锁定，请稍后重试", "DIRECTORY_LOCKED", status_code=409)
            profile_row.is_locked = True
            profile_row.lock_owner = f"run:{run_id}"
            profile_row.lock_run_id = run_id
            profile_row.locked_at = beijing_now()

            session.commit()

        start_time = beijing_now()
        cfg = get_settings()
        cdp_port = script.get("default_cdp_port") or 9222
        extra_env = {
            "CHROME_USER_DATA_DIR": str(profile_absolute_path),
            "CDP_PORT": str(cdp_port),
            "RUN_MODE": run_mode,
            "MYSQL_HOST": cfg.mysql_host,
            "MYSQL_PORT": str(cfg.mysql_port),
            "MYSQL_USER": cfg.mysql_user,
            "MYSQL_PASSWORD": cfg.mysql_password,
            "COOKIE_TABLE": row.cookie_table,
            "TXY_CHANNEL": row.channel,
            "TXY_SHOP_NAME": row.shop_name or "",
            "TXY_DNS": row.dns or "",
            "TXY_ACCOUNT": cfg.txy_account,
            "TXY_PASSWORD": cfg.txy_password,
            "TXY_MOBILE_PHONE": row.mobile_phone or "",
        }
        try:
            kill_chrome_for_profile(profile_absolute_path)
            kill_chrome_on_port(cdp_port)
        except Exception:
            logger.exception("清理旧 Chrome 进程异常 run_id=%s", run_id)

        timeout_seconds = row.repair_timeout_seconds or 600
        try:
            result = self.executor.execute(
                script_path=script_path,
                artifact_dir=artifact_dir,
                extra_env=extra_env,
                run_id=run_id,
                control_file=control_file,
                timeout_seconds=timeout_seconds,
                on_start=lambda pid: self._mark_running(run_id, pid),
            )
        except Exception as exc:
            # 执行异常：标记失败 + 释放锁（内部独立事务），并触发 EXCEPTION 自动排障
            dispatch_result = self._handle_execution_error(
                run_id, row, profile, exc, script_path=str(script_path), cdp_port=cdp_port
            )
            if not (dispatch_result or {}).get("dispatched"):
                # 未唤起排障：若该店有在途排障（RUNNING）则保留浏览器给在途 agent，否则兜底清理
                if (dispatch_result or {}).get("ticket_status") != "RUNNING":
                    self._safe_kill_chrome(profile_absolute_path, cdp_port, run_id)
            raise AppError(f"执行脚本失败: {exc}", "EXECUTION_FAILED")

        end_time = beijing_now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        status = result.get("status", "FAIL")
        exit_code = result.get("exit_code", -1)
        log_path = result.get("log_path")

        # 仅 SUCCESS 直接清理浏览器；FAIL/RISK 保留现场给自动排障（唤起/兜底时统一清理）
        if status == "SUCCESS":
            self._safe_kill_chrome(profile_absolute_path, cdp_port, run_id)

        with Session(self.engine) as session:
            sr = session.execute(
                select(ScriptRun).where(ScriptRun.run_id == run_id)
            ).scalar_one()
            sr.status = status if status in ("SUCCESS", "FAIL", "RISK") else "FAIL"
            sr.pid = result.get("pid")
            sr.exit_code = exit_code
            sr.log_file = log_path
            sr.stdout_file = result.get("stdout_path")
            sr.stderr_file = result.get("stderr_path")
            sr.start_time = start_time
            sr.end_time = end_time
            sr.duration_ms = duration_ms
            sr.error_message = result.get("error_message")

            result_path = artifact_dir / "result.json"
            if result_path.exists():
                sr.result_json = result_path.read_text(encoding="utf-8")

            profile_row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == effective_directory_id)
            ).scalar_one_or_none()
            if profile_row is not None and profile_row.lock_run_id == run_id:
                profile_row.is_locked = False
                profile_row.lock_owner = None
                profile_row.lock_run_id = None
                profile_row.locked_at = None

            row_ref = self._get_row(session, health_task_code)
            row_ref.last_run_status = status
            row_ref.last_repair_run_id = run_id
            row_ref.last_repaired_at = end_time
            row_ref.last_result_message = result.get("message", result.get("status", ""))

            if status == "SUCCESS":
                row_ref.status = "PASS"
            elif status == "RISK":
                row_ref.status = "PENDING"
                risk_message = result.get("message", result.get("risk_type", "RISK"))
                row_ref.last_result_message = risk_message
                try:
                    send_feishu_notification(
                        title=f"修复遇风控: {row_ref.health_task_name or health_task_code}",
                        message=risk_message,
                        fields={
                            "任务编码": health_task_code,
                            "脚本": sr.script_code or "",
                            "启动目录": sr.directory_key or "",
                            "运行实例": run_id,
                            "结果信息": risk_message,
                        },
                    )
                except Exception:
                    logger.exception("发送风控飞书通知异常 [%s]", health_task_code)
            else:
                row_ref.status = "FAIL"

            session.commit()
            session.refresh(row_ref)

            # ── 自动排障触发（主事务已提交；内部独立 Session，见 REQ-011 / SCOPE-019）──
            # FAIL / RISK 都唤起：RISK 由排障 agent 判级，遇人机验证即转人工（OUT-012）
            if status in ("FAIL", "RISK"):
                dispatch_result = trigger_auto_repair(
                    self.engine,
                    channel=row.channel,
                    shop_name=row.shop_name,
                    cdp_port=cdp_port,
                    script_code=script["script_code"],
                    script_path=str(script_path),
                    health_task_code=health_task_code,
                    health_task_name=row_ref.health_task_name,
                    script_run_id=sr.id,
                    issue_type=status,  # FAIL / RISK
                    error_message=(
                        result.get("error_message")
                        or result.get("message")
                        or f"修复脚本执行 {status}"
                    ),
                )
                if not dispatch_result.get("dispatched"):
                    # 未唤起：若该店有在途排障（RUNNING）则保留浏览器给在途 agent，否则兜底清理
                    if dispatch_result.get("ticket_status") != "RUNNING":
                        self._safe_kill_chrome(profile_absolute_path, cdp_port, run_id)

            self.log_service.write(
                run_id=run_id,
                run_type="REPAIR",
                task_id=row_ref.id,
                status=status,
                title=row_ref.health_task_name or health_task_code,
                message=result.get("message", result.get("status", "")) or "",
                log_file_path=str(artifact_dir / "run.log") if (artifact_dir / "run.log").exists() else None,
            )

            return self._serialize(row_ref)

    def delete_task(self, health_task_code: str) -> None:
        from app.models.run_log import TaskRunLog
        from app.models.script_run import ScriptRun
        from sqlalchemy import delete

        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)

            locked_run_ids = session.execute(
                select(ScriptRun.run_id).where(ScriptRun.health_task_code == health_task_code)
            ).scalars().all()
            if locked_run_ids:
                for profile_row in session.execute(
                    select(ProfileRegistry).where(ProfileRegistry.lock_run_id.in_(locked_run_ids))
                ).scalars().all():
                    profile_row.is_locked = False
                    profile_row.lock_owner = None
                    profile_row.lock_run_id = None
                    profile_row.locked_at = None

            session.execute(
                delete(TaskRunLog).where(TaskRunLog.task_id == row.id)
            )
            session.execute(
                delete(ScriptRun).where(ScriptRun.health_task_code == health_task_code)
            )
            session.delete(row)
            session.commit()

    # ── 时间线 ──

    def get_timeline(self, health_task_code: str) -> list[dict[str, object]]:
        from app.models.run_log import TaskRunLog
        from app.models.script_run import ScriptRun

        with Session(self.engine) as session:
            task = self._get_row(session, health_task_code)

            check_logs: list[dict[str, object]] = []
            log_rows = session.execute(
                select(TaskRunLog).where(
                    TaskRunLog.task_id == task.id,
                    TaskRunLog.run_type == "CHECK",
                )
            ).scalars().all()
            for log in log_rows:
                check_logs.append({
                    "time": log.created_at.isoformat() if log.created_at else "",
                    "action": "执行检测",
                    "action_type": "check",
                    "result": log.status,
                    "detail": log.message,
                })

            repair_logs: list[dict[str, object]] = []
            script_rows = session.execute(
                select(ScriptRun).where(
                    ScriptRun.health_task_code == health_task_code,
                ).order_by(ScriptRun.start_time.asc())
            ).scalars().all()
            for sr in script_rows:
                script_name = sr.script_code
                if sr.script_code:
                    sn = session.execute(
                        select(ScriptRegistry.script_name).where(ScriptRegistry.script_code == sr.script_code)
                    ).scalar_one_or_none()
                    if sn:
                        script_name = sn
                log_content = f"运行模式: {sr.run_mode}\nPID: {sr.pid}\n耗时: {sr.duration_ms}ms\n退出码: {sr.exit_code}"
                if sr.log_file:
                    log_path = Path(sr.log_file)
                    if log_path.is_file():
                        try:
                            content = log_path.read_text(encoding="utf-8")
                            if content.strip():
                                log_content += "\n\n--- 完整日志 ---\n" + content
                        except Exception:
                            pass
                repair_logs.append({
                    "time": sr.start_time.isoformat() if sr.start_time else "",
                    "action": f"执行修复脚本: {script_name}",
                    "action_type": "repair",
                    "result": sr.status,
                    "detail": log_content,
                })

            timeline = check_logs + repair_logs
            timeline.sort(key=lambda x: x["time"], reverse=True)
            return timeline

    # ── 内部 ──

    def _get_row_internal(self, health_task_code: str) -> HealthTask:
        with Session(self.engine) as session:
            return self._get_row(session, health_task_code)

    def _get_row(self, session: Session, health_task_code: str) -> HealthTask:
        row = session.execute(
            select(HealthTask).where(HealthTask.health_task_code == health_task_code)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("健康检测任务不存在", "HEALTH_TASK_NOT_FOUND", status_code=404)
        return row

    def _get_script(self, script_id: int) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.id == script_id)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            return {
                "id": row.id,
                "script_code": row.script_code,
                "profile_key": row.profile_key,
                "script_dir": row.script_dir,
                "main_file": row.main_file,
                "default_run_mode": row.default_run_mode,
                "default_cdp_port": row.default_cdp_port,
            }

    def _get_profile(self, directory_id: int) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == directory_id)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("目录不存在", "DIRECTORY_NOT_FOUND", status_code=404)
            return {
                "id": row.id,
                "profile_key": row.profile_key,
                "relative_path": row.relative_path,
            }

    def _get_profile_by_key(self, profile_key: str) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.profile_key == profile_key)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("目录不存在", "DIRECTORY_NOT_FOUND", status_code=404)
            return {
                "id": row.id,
                "profile_key": row.profile_key,
                "relative_path": row.relative_path,
            }

    def _resolve_profile_path(self, relative_path: str) -> Path:
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return resolve_runtime_path(self.runtime_root, relative_path)

    def _mark_running(self, run_id: str, pid: int) -> None:
        """子进程一启动即回调落 RUNNING + pid + start_time（executor 在 Popen 后回调）。

        此前 commit PENDING → Popen 之间存在窗口：父进程若在此窗口退出，run 无 pid、
        无法与在跑实例区分、reap 无从核对。本回调把窗口缩到最小，保证此后
        reap 能按 pid/start_time 核对与回收，不再留下不可辨的 PENDING 僵尸。
        """
        try:
            with Session(self.engine) as session:
                sr = session.execute(
                    select(ScriptRun).where(ScriptRun.run_id == run_id)
                ).scalar_one_or_none()
                if sr is not None:
                    sr.status = "RUNNING"
                    sr.pid = pid
                    sr.start_time = sr.start_time or beijing_now()
                    session.commit()
        except Exception:
            logger.exception("标记 ScriptRun RUNNING 失败 run_id=%s pid=%s", run_id, pid)

    @staticmethod
    def _run_base_time(run: ScriptRun, now: datetime) -> datetime:
        """回收判定的基准时间。

        start_time 由 beijing_now 写入（本地时间 naive）；created_at 为 DB func.now()
        （SQLite 存 UTC naive）。start_time 缺失（父进程死在写 start 前）的记录把
        created_at 折算 +8h 到本地，避免时区差导致被误判为立即超时而误回收。
        """
        if run.start_time is not None:
            return run.start_time
        if run.created_at is not None:
            return run.created_at + timedelta(hours=8)
        return now

    def _is_run_stale(self, run: ScriptRun, now: datetime) -> bool:
        timeout = run.timeout_seconds or 600
        return now >= (self._run_base_time(run, now) + timedelta(seconds=timeout + STALE_RUN_GRACE_SECONDS))

    def _reclaim_one(self, session: Session, run: ScriptRun, now: datetime) -> bool:
        """单条回收（同事务内）：仅当确实僵死才执行，返回是否回收。

        仅当锁仍指向本 run 才释放，避免误清被后续实例更新的锁。
        """
        if not self._is_run_stale(run, now):
            return False
        if run.pid:
            kill_process_tree(run.pid)
        run.status = "FAIL"
        run.end_time = now
        run.error_message = "STALE_RUN_RECLAIM: 前次实例超时僵死，启动本次执行前自动回收"
        if run.directory_id is not None:
            profile_row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == run.directory_id)
            ).scalar_one_or_none()
            if profile_row is not None and profile_row.lock_run_id == run.run_id:
                profile_row.is_locked = False
                profile_row.lock_owner = None
                profile_row.lock_run_id = None
                profile_row.locked_at = None
        return True

    def reap_stale_runs(self) -> int:
        """回收所有超时未收尾的 ScriptRun，并同步释放对应目录锁（幂等）。

        由调度每 tick 调用；也可在执行前惰性调用。返回回收条数。
        """
        now = beijing_now()
        reclaimed = 0
        with Session(self.engine) as session:
            runs = session.execute(
                select(ScriptRun).where(ScriptRun.status.in_(RUNNING_STATUSES))
            ).scalars().all()
            for run in runs:
                if self._reclaim_one(session, run, now):
                    reclaimed += 1
            if reclaimed:
                session.commit()
        if reclaimed:
            logger.warning("reap_stale_runs: 自动回收 %s 条僵死执行记录", reclaimed)
        return reclaimed

    def _handle_execution_error(
        self,
        run_id: str,
        task: HealthTask,
        profile: dict[str, object],
        exc: Exception,
        script_path: str = "",
        cdp_port: int = 9222
    ) -> None:
        with Session(self.engine) as session:
            sr = session.execute(
                select(ScriptRun).where(ScriptRun.run_id == run_id)
            ).scalar_one_or_none()
            if sr:
                sr.status = "FAIL"
                sr.error_message = str(exc)
                sr.end_time = beijing_now()

            profile_row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == profile["id"])
            ).scalar_one_or_none()
            if profile_row:
                profile_row.is_locked = False
                profile_row.lock_owner = None
                profile_row.lock_run_id = None
                profile_row.locked_at = None

            task_ref = self._get_row(session, task.health_task_code)
            task_ref.last_run_status = "FAIL"
            task_ref.last_result_message = str(exc)

            # 缓存触发所需标量（with 退出后对象过期，无法再访问属性）
            exc_ctx = {
                "channel": task.channel,
                "shop_name": task.shop_name or "",
                "health_task_code": task.health_task_code,
                "health_task_name": task.health_task_name,
                "script_run_id": sr.id if sr else None,
            }
            session.commit()

        # 主事务已提交：触发 EXCEPTION 自动排障（独立 Session，见 REQ-011）；
        # 返回 dispatch_result 供调用方决定是否兜底清理现场浏览器
        dispatch_result: dict[str, object] = {"dispatched": False}
        if sr is not None and exc_ctx["channel"]:
            try:
                from app.services.agent_repair_dispatcher import trigger_auto_repair

                dispatch_result = trigger_auto_repair(
                    self.engine,
                    channel=exc_ctx["channel"],
                    shop_name=exc_ctx["shop_name"],
                    cdp_port=cdp_port,
                    script_path=script_path or None,
                    health_task_code=exc_ctx["health_task_code"],
                    health_task_name=exc_ctx["health_task_name"],
                    script_run_id=exc_ctx["script_run_id"],
                    issue_type="EXCEPTION",
                    error_message=f"执行异常崩溃: {exc}",
                )
            except Exception:
                logger.exception("[AutoRepair] 异常处理中触发自动排障失败")
        return dispatch_result

    def _validate_payload(
        self, payload: dict[str, object], is_create: bool
    ) -> None:
        if is_create:
            required = ["health_task_name", "channel", "check_url"]
            for field in required:
                if not payload.get(field):
                    raise AppError(f"{field} 不能为空", "INVALID_PAYLOAD")

        http_method = payload.get("http_method")
        if http_method is not None and http_method not in ALLOWED_METHODS:
            raise AppError(f"不支持的请求方法: {http_method}", "INVALID_PAYLOAD")

        run_mode = payload.get("repair_run_mode")
        if run_mode is not None and run_mode not in ALLOWED_RUN_MODES:
            raise AppError(
                f"运行模式必须为 HEADLESS 或 HEADED，收到: {run_mode}",
                "INVALID_PAYLOAD",
            )

    @staticmethod
    def _mask_sensitive(text: str) -> str:
        if not text:
            return text
        masked = text
        sensitive_keys = re.compile(
            r'(?i)("(?:cookie|set-cookie|token|access_token|refresh_token|'
            r'password|passwd|secret|api[_-]?key|authorization|captcha|sms[_-]?code|'
            r'verify[_-]?code|mobile|phone|phone_number)["\']?\s*[:=]\s*["\']?)([^"\',}\s][^"\',}]{0,80})',
        )

        def _mask_value(match: re.Match[str]) -> str:
            prefix = match.group(1)
            return f"{prefix}***"

        masked = sensitive_keys.sub(_mask_value, masked)

        masked = re.sub(
            r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}",
            r"\1 ***",
            masked,
        )

        masked = re.sub(
            r"(?<!\d)1[3-9]\d{9}(?!\d)",
            "138****0000",
            masked,
        )

        return masked

    def _match_rule(
        self, rule_json: str | None, status_code: int, body: object
    ) -> bool:
        if not rule_json:
            return False
        try:
            rule = json.loads(rule_json)
        except json.JSONDecodeError:
            return False
        if not isinstance(rule, dict):
            return False
        if "status_code" in rule:
            return status_code == int(rule["status_code"])
        if "contains" in rule:
            pattern = rule["contains"]
            if isinstance(pattern, str):
                body_str = json.dumps(body, ensure_ascii=False) if body is not None else str(body)
                try:
                    return bool(re.search(pattern, body_str))
                except re.error:
                    return pattern in body_str
            if isinstance(pattern, dict):
                path = str(pattern.get("path", ""))
                expected = str(pattern.get("value", ""))
                actual = self._extract_path(body, path)
                return expected in str(actual)
            return False
        if "equals" in rule:
            val = rule["equals"]
            if isinstance(val, str):
                body_str = json.dumps(body, ensure_ascii=False) if body is not None else str(body)
                return val == body_str
            if isinstance(val, dict):
                path = str(val.get("path", ""))
                expected = val.get("value", "")
                actual = self._extract_path(body, path)
                return actual == expected
            return False
        return False

    def _extract_path(self, payload: object, path: str) -> object:
        current = payload
        for part in [s for s in path.split(".") if s]:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            else:
                return None
        return current

    def _serialize(self, row: HealthTask) -> dict[str, object]:
        return {
            "id": row.id,
            "health_task_code": row.health_task_code,
            "health_task_name": row.health_task_name,
            "enabled": row.enabled,
            "cookie_table": row.cookie_table,
            "channel": row.channel,
            "shop_name": row.shop_name,
            "mobile_phone": row.mobile_phone,
            "dns": row.dns,
            "check_url": row.check_url,
            "http_method": row.http_method,
            "http_headers": row.http_headers,
            "http_body": row.http_body,
            "success_rule": row.success_rule,
            "failure_rule": row.failure_rule,
            "cron_expression": row.cron_expression,
            "check_timeout_seconds": row.check_timeout_seconds,
            "retry_count": row.retry_count,
            "last_checked_at": row.last_checked_at,
            "next_run_at": row.next_run_at,
            "auto_repair_enabled": row.auto_repair_enabled,
            "repair_cron_expression": row.repair_cron_expression,
            "repair_script_id": row.repair_script_id,
            "repair_directory_id": row.repair_directory_id,
            "repair_run_mode": row.repair_run_mode,
            "repair_script_config": row.repair_script_config,
            "repair_timeout_seconds": row.repair_timeout_seconds,
            "status": row.status,
            "last_run_status": row.last_run_status,
            "last_result_message": row.last_result_message,
            "last_repaired_at": row.last_repaired_at,
            "last_repair_run_id": row.last_repair_run_id,
            "updated_at": row.updated_at,
        }
