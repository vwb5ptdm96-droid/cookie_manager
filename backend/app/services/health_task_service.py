from __future__ import annotations

import json
import logging
import re
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
from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService
from app.services.local_windows_executor import LocalWindowsExecutor
from app.services.notification_service import send_feishu_notification
from app.services.run_log_service import RunLogService


ALLOWED_CHANNELS = {"KUAISHOU", "TAOBAO", "TMALL", "ALIMAMA", "JD", "PDD"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ALLOWED_RUN_MODES = {"HEADLESS", "HEADED"}
RUNNING_STATUSES = {"PENDING", "RUNNING", "PAUSED", "CANCELING"}


class HealthTaskService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        self.executor = LocalWindowsExecutor()
        # cookie 查询走云端 MySQL，本地 SQLite 没有 ods 表
        cookie_engine = create_mysql_engine() or engine
        self.legacy_cookie_service = LegacyCookieService(engine=cookie_engine)
        self.log_service = RunLogService(engine=engine)

    # ── Chrome 进程清理 ──

    @staticmethod
    def _kill_chrome_for_profile(profile_path: Path) -> None:
        """杀掉占用指定 user-data-dir 的 Chrome 进程（包括子进程），防止缓存污染。"""
        import base64
        import subprocess

        profile_str = str(profile_path).replace("/", "\\")
        # 用 -EncodedCommand 解决中文路径编码问题
        ps_script = (
            f'Get-CimInstance Win32_Process -Filter "name=\'chrome.exe\'" | '
            f'Where-Object {{ $_.CommandLine -like \'*--user-data-dir={profile_str.replace("'", "''")}*\' }} | '
            f'Stop-Process -Force -PassThru'
        )
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode()
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout.strip():
                killed = [l for l in result.stdout.strip().splitlines() if l.strip()]
                if killed:
                    logger.info("Chrome cleanup for %s: killed %d process(s)", profile_str, len(killed))
        except subprocess.TimeoutExpired:
            logger.warning("Chrome cleanup timed out for %s", profile_str)
        except Exception as exc:
            logger.warning("Chrome cleanup error for %s: %s", profile_str, exc)

        # Chrome 被强制杀掉后会残留 lockfile，导致下次无法启动
        for lock_file in ("lockfile", "SingletonLock", "SingletonSocket"):
            p = profile_path / lock_file
            if p.is_file():
                try:
                    p.unlink()
                    logger.info("Removed Chrome lockfile: %s", p)
                except Exception as exc:
                    logger.warning("Failed to remove lockfile %s: %s", p, exc)

    @staticmethod
    def _kill_chrome_on_port(cdp_port: int) -> None:
        """通过端口号杀掉占用 CDP 端口的 Chrome 进程（兜底方案）。"""
        import subprocess

        try:
            # netstat 找 PID
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if f":{cdp_port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1] if parts else ""
                    if pid.isdigit():
                        subprocess.run(
                            ["taskkill", "-f", "-pid", pid],
                            capture_output=True, text=True, timeout=5,
                        )
                        logger.info("Killed Chrome on port %d (PID %s)", cdp_port, pid)
        except Exception as exc:
            logger.warning("Port-based Chrome cleanup failed for port %d: %s", cdp_port, exc)

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
        """复制一个健康检测任务，生成新的编码和名称（副本）。"""
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
        """立即执行检测：查 cookie → 发请求 → 评规则 → 记日志。"""
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

            # ── 1. 查 cookie ──
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
                                # JSON 数组：[{"name":"c1","value":"v1"}, ...]
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
                    # 如果 JSON cookie 未解析出内容，回退到 str_cookie
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

            # ── 2. 组装请求 ──
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

            # ── 3. 发 HTTP 请求 ──
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
                response_body_preview = body_str[:50]
                add_step(f"✅ HTTP 请求完成: 状态码 {response_status}")
                add_step(f"响应内容:\n{body_str[:2000]}")

                # ── 4. 评规则 ──
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

        # ── 5. 失败时飞书通知 ──
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

            # ── 6. 自动修复（如果配置了） ──
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

    def execute_repair(self, health_task_code: str) -> dict[str, object]:
        """完整修复流程：串行排队 → 去重检查 → 目录锁 → 创建 ScriptRun → 执行 → 释放锁 → 更新状态。"""
        with _repair_lock:
            return self._do_execute_repair(health_task_code, force=False)

    def execute_scheduled_repair(self, health_task_code: str) -> dict[str, object]:
        """调度触发的修复执行，跳过 auto_repair_enabled 检查。"""
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

        # ── 0. 确定启动目录：优先脚本库关联的目录，其次健康检测任务配置 ──
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

        # ── 1. 去重检查 ──
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
                run_ids = ", ".join(e.run_id for e in existing)
                raise AppError(
                    f"相同脚本+目录的执行实例已存在（{run_ids}），跳过执行",
                    "DUPLICATE_RUN",
                )

        # ── 2. 读取关联资源 ──
        profile = self._get_profile(effective_directory_id)
        profile_absolute_path = self._resolve_profile_path(profile["relative_path"])
        script_absolute_dir = resolve_runtime_path(self.runtime_root, script["script_dir"])
        script_path = script_absolute_dir / script["main_file"]

        run_mode = row.repair_run_mode or script["default_run_mode"] or "HEADLESS"

        # ── 3. 创建 artifact 目录 ──
        run_id = f"run_{uuid4().hex[:12]}"
        artifact_dir = self.runtime_root / "artifacts" / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        control_file = str(artifact_dir / "control.json")

        # ── 4. 写入 config.json ──
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

        # ── 5. 创建 ScriptRun + 锁定目录 ──
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

            # 锁定目录
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

        # ── 6. 执行脚本 ──
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
        # 清理同目录的旧 Chrome 进程，避免连接旧实例或缓存污染
        self._kill_chrome_for_profile(profile_absolute_path)
        self._kill_chrome_on_port(cdp_port)
        try:
            result = self.executor.execute(
                script_path=script_path,
                artifact_dir=artifact_dir,
                extra_env=extra_env,
                run_id=run_id,
                control_file=control_file,
            )
        except Exception as exc:
            self._handle_execution_error(run_id, row, profile, exc)
            raise AppError(f"执行脚本失败: {exc}", "EXECUTION_FAILED")
        finally:
            # 脚本结束后清理 Chrome，确保不残留
            self._kill_chrome_for_profile(profile_absolute_path)
            self._kill_chrome_on_port(cdp_port)

        end_time = beijing_now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # ── 7. 更新状态 ──
        status = result.get("status", "FAIL")
        exit_code = result.get("exit_code", -1)
        log_path = result.get("log_path")

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

            # 释放目录锁
            profile_row = session.execute(
                select(ProfileRegistry).where(ProfileRegistry.id == effective_directory_id)
            ).scalar_one()
            profile_row.is_locked = False
            profile_row.lock_owner = None
            profile_row.lock_run_id = None
            profile_row.locked_at = None

            # 更新 HealthTask
            row_ref = self._get_row(session, health_task_code)
            row_ref.last_run_status = status
            row_ref.last_repair_run_id = run_id
            row_ref.last_repaired_at = end_time
            row_ref.last_result_message = result.get("message", result.get("status", ""))

            if status == "SUCCESS":
                row_ref.status = "PASS"
            elif status == "RISK":
                row_ref.status = "PENDING"
                row_ref.last_result_message = (
                    result.get("message", result.get("risk_type", "RISK"))
                )
                # TODO: 创建 RepairTicket
            else:
                row_ref.status = "FAIL"

            session.commit()
            session.refresh(row_ref)
            return self._serialize(row_ref)

    def delete_task(self, health_task_code: str) -> None:
        """删除健康检测任务及关联的 run_log 和 script_run 记录。"""
        from app.models.run_log import TaskRunLog
        from app.models.script_run import ScriptRun
        from sqlalchemy import delete

        with Session(self.engine) as session:
            row = self._get_row(session, health_task_code)

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
        """聚合该任务的所有检测和修复执行记录，按时间排序。"""
        from app.models.run_log import TaskRunLog
        from app.models.script_run import ScriptRun

        with Session(self.engine) as session:
            task = self._get_row(session, health_task_code)

            # 1) 检测日志 (task_run_log)
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

            # 2) 修复脚本执行 (script_run)
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

            # 3) 合并按时间倒序（最近在前）
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

    def _handle_execution_error(
        self, run_id: str, task: HealthTask, profile: dict[str, object], exc: Exception
    ) -> None:
        """脚本执行异常时的清理：释放锁、标记失败。"""
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

            session.commit()

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
                # 正则匹配整个响应体
                body_str = json.dumps(body, ensure_ascii=False) if body is not None else str(body)
                try:
                    return bool(re.search(pattern, body_str))
                except re.error:
                    return pattern in body_str
            # 兼容旧格式：{contains: {path, value}}
            if isinstance(pattern, dict):
                path = str(pattern.get("path", ""))
                expected = str(pattern.get("value", ""))
                actual = self._extract_path(body, path)
                return expected in str(actual)
            return False
        if "equals" in rule:
            val = rule["equals"]
            if isinstance(val, str):
                # 直接比较整个响应体
                body_str = json.dumps(body, ensure_ascii=False) if body is not None else str(body)
                return val == body_str
            # 兼容旧格式：{equals: {path, value}}
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
