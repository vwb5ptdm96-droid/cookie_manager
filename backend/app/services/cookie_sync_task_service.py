from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.builtin_scripts.health_request import perform_health_request
from app.core.config import create_mysql_engine
from app.core.errors import AppError
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.models.cookie_sync_task import CookieSyncTask
from app.services.cookie_sync_service import CookieSyncService
from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService
from app.services.notification_service import send_feishu_notification
from app.services.run_log_service import RunLogService

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
# 未配置 cron 时的最小检测间隔（与健康检测任务一致，5 分钟）
DEFAULT_MIN_INTERVAL_SECONDS = 300


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


class CookieSyncTaskService:
    """Cookie 采集任务：检测失效 → 扩展采集 → 写回 → 复检 闭环。

    - 检测复用健康检测逻辑：读 legacy cookie → 构造请求 → 成功/失败规则判定
    - 失效时按映射反向查 (worker_id, domain) → 下发定向采集任务 → SYNCING
    - 上报写回后复检（recheck_after_sync）；超时或无映射 → FAIL + 飞书
    - 不绑定修复脚本与目录（Spec REQ-007）
    """

    def __init__(
        self,
        engine: Engine,
        cookie_engine: Engine | None = None,
        runtime_root=None,
        notifier=None,
    ) -> None:
        self.engine = engine
        self.runtime_root = runtime_root
        # expire_on_commit=False：commit 后对象属性保持已加载，跨 Session 可安全访问
        self.session_factory = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        # ods 写回/读取走云端 MySQL；无配置或测试注入时回退主库
        effective_cookie_engine = cookie_engine or (create_mysql_engine() or engine)
        self.legacy_cookie_service = LegacyCookieService(engine=effective_cookie_engine)
        self.cookie_sync_service = CookieSyncService(
            engine=engine, cookie_engine=effective_cookie_engine
        )
        self.log_service = RunLogService(engine=engine)
        # 测试注入 fake 关闭飞书
        self.notifier = notifier or send_feishu_notification

    # ── CRUD ──

    def list_tasks(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CookieSyncTask).order_by(CookieSyncTask.created_at.desc())
            ).scalars().all()
        return [self._serialize(row) for row in rows]

    def get_task(self, cookie_sync_task_code: str) -> dict[str, object]:
        with self.session_factory() as session:
            return self._serialize(self._get_row(session, cookie_sync_task_code))

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        self._validate_payload(payload, is_create=True)
        code = f"cst_{uuid4().hex[:10]}"
        with self.session_factory() as session:
            row = CookieSyncTask(
                cookie_sync_task_code=code,
                cookie_sync_task_name=payload["cookie_sync_task_name"].strip(),
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
                sync_wait_timeout_seconds=payload.get("sync_wait_timeout_seconds", 180),
                status="PENDING",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def update_task(self, code: str, payload: dict[str, object]) -> dict[str, object]:
        self._validate_payload(payload, is_create=False)
        simple_fields = {
            "cookie_sync_task_name": str,
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
            "sync_wait_timeout_seconds": int,
        }
        with self.session_factory() as session:
            row = self._get_row(session, code)
            for field, expected_types in simple_fields.items():
                if field in payload:
                    value = payload[field]
                    if value is not None and not isinstance(value, expected_types):
                        raise AppError(f"{field} 类型不正确", "INVALID_PAYLOAD")
                    setattr(row, field, value)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def toggle_task(self, code: str, enabled: bool) -> dict[str, object]:
        with self.session_factory() as session:
            row = self._get_row(session, code)
            row.enabled = enabled
            if not enabled:
                row.status = "DISABLED"
            elif row.status == "DISABLED":
                row.status = "PENDING"
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def clone_task(self, code: str) -> dict[str, object]:
        with self.session_factory() as session:
            source = self._get_row(session, code)
            row = CookieSyncTask(
                cookie_sync_task_code=f"cst_{uuid4().hex[:10]}",
                cookie_sync_task_name=f"{source.cookie_sync_task_name} (副本)",
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
                sync_wait_timeout_seconds=source.sync_wait_timeout_seconds,
                status="PENDING",
                enabled=True,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def delete_task(self, code: str) -> None:
        with self.session_factory() as session:
            row = self._get_row(session, code)
            session.delete(row)
            session.commit()

    # ── 检测与扩展采集闭环 ──

    def execute_check(self, code: str) -> dict[str, object]:
        """立即检测：PASS → PASS；FAIL → 反查映射下发采集 → SYNCING / 无映射 FAIL。"""
        run_id = f"sync_check_{uuid4().hex[:12]}"
        steps: list[str] = []
        response_preview = ""

        def add_step(msg: str) -> None:
            ts = beijing_now().strftime("%H:%M:%S")
            steps.append(f"[{ts}] {msg}")

        with self.session_factory() as session:
            row = self._get_row(session, code)
            if not row.enabled:
                raise AppError("该采集任务已停用", "TASK_DISABLED")

            add_step(f"开始检测: {row.cookie_sync_task_name}")
            check_pass, check_message, response_preview = self._perform_check(
                session, row, add_step
            )
            row.last_checked_at = beijing_now()

            if check_pass:
                row.status = "PASS"
                row.last_run_status = "SUCCESS"
                row.last_result_message = check_message
                row.sync_deadline_at = None
                session.commit()
            else:
                mapping = self._find_mapping(session, row)
                if mapping is None:
                    row.status = "FAIL"
                    row.last_run_status = "FAIL"
                    row.last_result_message = "检测失败且无对应采集映射"
                    row.sync_deadline_at = None
                    session.commit()
                    add_step("❌ 检测失败且无对应采集映射")
                    add_step("⚠️ 飞书通知运维")
                    self._notify_fail(row, f"{check_message}；无对应采集映射", response_preview)
                else:
                    try:
                        result = self.cookie_sync_service.create_request(
                            domains=[mapping.domain],
                            worker_ids=[mapping.worker_id],
                            source_task_id=row.id,
                        )
                    except SQLAlchemyError:
                        session.rollback()
                        logger.exception("下发采集任务失败 code=%s", code)
                        row.status = "FAIL"
                        row.last_run_status = "FAIL"
                        row.last_result_message = "检测失败，下发采集任务失败"
                        session.commit()
                        self._notify_fail(row, "检测失败，下发采集任务失败", response_preview)
                    else:
                        task_id = result["task_id"]
                        row.status = "SYNCING"
                        row.last_run_status = "SYNCING"
                        row.last_result_message = (
                            f"检测失败，已下发采集任务 {task_id} 给 {mapping.worker_id}，"
                            f"等待上报（{row.sync_wait_timeout_seconds}s）"
                        )
                        row.sync_deadline_at = beijing_now() + timedelta(
                            seconds=row.sync_wait_timeout_seconds
                        )
                        session.commit()
                        add_step(f"⚠️ 检测失败，已下发采集任务 {task_id} 给 {mapping.worker_id}，进入 SYNCING")

        status = self._status_for_log(row)
        self.log_service.write(
            run_id=run_id,
            run_type="COOKIE_SYNC",
            task_id=row.id,
            status=status,
            title=row.cookie_sync_task_name,
            message="\n".join(steps),
        )
        result = self._serialize(row)
        result["check_detail"] = "\n".join(steps)
        return result

    def recheck_after_sync(self, task_id: int) -> dict[str, object]:
        """扩展上报写回后复检：重新执行检测，PASS 则恢复，仍失败则 FAIL + 飞书。"""
        run_id = f"sync_recheck_{uuid4().hex[:12]}"
        steps: list[str] = []
        response_preview = ""

        def add_step(msg: str) -> None:
            ts = beijing_now().strftime("%H:%M:%S")
            steps.append(f"[{ts}] {msg}")

        with self.session_factory() as session:
            row = self._get_row_by_id(session, task_id)
            add_step("扩展已上报，开始复检")
            check_pass, check_message, response_preview = self._perform_check(
                session, row, add_step
            )
            row.last_checked_at = beijing_now()
            row.sync_deadline_at = None
            if check_pass:
                row.status = "PASS"
                row.last_run_status = "SUCCESS"
                row.last_result_message = f"复检通过: {check_message}"
            else:
                row.status = "FAIL"
                row.last_run_status = "FAIL"
                row.last_result_message = f"复检仍失败: {check_message}"
            session.commit()

        if not check_pass:
            add_step("❌ 复检仍失败")
            add_step("⚠️ 飞书通知运维")
            self._notify_fail(row, f"复检仍失败: {check_message}", response_preview)

        self.log_service.write(
            run_id=run_id,
            run_type="COOKIE_SYNC",
            task_id=row.id,
            status=row.last_run_status or "FAIL",
            title=row.cookie_sync_task_name,
            message="\n".join(steps),
        )
        result = self._serialize(row)
        result["check_detail"] = "\n".join(steps)
        return result

    def fail_on_timeout(self, task_id: int) -> dict[str, object]:
        """等待扩展上报超时 → FAIL + 飞书。"""
        run_id = f"sync_timeout_{uuid4().hex[:12]}"
        steps: list[str] = []

        with self.session_factory() as session:
            row = self._get_row_by_id(session, task_id)
            steps.append(f"[{beijing_now().strftime('%H:%M:%S')}] 等待扩展上报超时，标记 FAIL")
            row.status = "FAIL"
            row.last_run_status = "FAIL"
            row.last_result_message = "等待扩展上报超时"
            row.sync_deadline_at = None
            session.commit()

        self._notify_fail(row, "等待扩展上报超时", "")
        self.log_service.write(
            run_id=run_id,
            run_type="COOKIE_SYNC",
            task_id=row.id,
            status="FAIL",
            title=row.cookie_sync_task_name,
            message="\n".join(steps),
        )
        result = self._serialize(row)
        result["check_detail"] = "\n".join(steps)
        return result

    # ── 检测核心（复用健康检测逻辑）──

    def _perform_check(
        self, session: Session, row: CookieSyncTask, add_step
    ) -> tuple[bool, str, str]:
        """读 legacy cookie → 构造请求 → 发请求 → 判规则。

        返回 (是否通过, 结论消息, 响应体预览)。失败时不会写库，由调用方决定后续动作。
        """
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

        response_preview = ""
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
            response_preview = masked_body[:50]
            add_step(f"✅ HTTP 请求完成: 状态码 {response_status}")
            add_step(f"响应内容:\n{masked_body[:2000]}")

            failure_hit = self._match_rule(row.failure_rule, response_status, response_body)
            success_rule_exists = bool(row.success_rule)
            success_hit = self._match_rule(row.success_rule, response_status, response_body)

            if failure_hit:
                return False, f"检测失败: 命中失败规则 (状态码 {response_status})", response_preview
            if success_hit:
                return True, f"检测通过: 命中成功规则 (状态码 {response_status})", response_preview
            if success_rule_exists:
                return False, f"检测失败: 未命中成功规则 (状态码 {response_status})", response_preview
            return True, f"检测通过: 状态码 {response_status}", response_preview
        except AppError as exc:
            add_step(f"❌ HTTP 请求失败: {exc.message}")
            return False, f"检测请求失败: {exc.message}", response_preview
        except Exception as exc:
            add_step(f"❌ 检测异常: {exc}")
            return False, f"检测异常: {exc}", response_preview

    def _find_mapping(self, session: Session, row: CookieSyncTask) -> CookieSyncMapping | None:
        """按业务键反查映射 (worker_id, domain)。

        优先精确匹配全部业务键；无命中时放宽到 channel + dns。
        """
        cond = (
            (CookieSyncMapping.channel == row.channel)
            & ((CookieSyncMapping.dns == row.dns) if row.dns else True)
        )
        if row.shop_name:
            cond &= (CookieSyncMapping.shop_name == row.shop_name) | (CookieSyncMapping.shop_name.is_(None))
        if row.mobile_phone:
            cond &= (CookieSyncMapping.mobile_phone == row.mobile_phone) | (CookieSyncMapping.mobile_phone.is_(None))

        mapping = session.execute(select(CookieSyncMapping).where(cond)).scalars().first()
        if mapping is not None:
            return mapping

        # 放宽：只要 channel + dns 命中即可（业务记录一般以 dns 为强定位）
        fallback = session.execute(
            select(CookieSyncMapping).where(
                CookieSyncMapping.channel == row.channel,
                CookieSyncMapping.dns == row.dns,
            )
        ).scalars().first()
        return fallback

    def _notify_fail(self, row: CookieSyncTask, message: str, response_preview: str) -> None:
        try:
            self.notifier(
                title=f"Cookie 采集任务失败: {row.cookie_sync_task_name or row.cookie_sync_task_code}",
                message=message,
                fields={
                    "任务编码": row.cookie_sync_task_code,
                    "检测 URL": row.check_url or "",
                    "请求方法": row.http_method or "",
                    "采集映射": "已下发等待上报" if row.status == "SYNCING" else "",
                    "结果信息": message,
                    "响应体预览": response_preview,
                },
            )
        except Exception:
            logger.exception("发送采集任务飞书通知异常 [%s]", row.cookie_sync_task_code)

    # ── 内部工具 ──

    def _get_row(self, session: Session, code: str) -> CookieSyncTask:
        row = session.execute(
            select(CookieSyncTask).where(CookieSyncTask.cookie_sync_task_code == code)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("Cookie 采集任务不存在", "COOKIE_SYNC_TASK_NOT_FOUND", status_code=404)
        return row

    def _get_row_by_id(self, session: Session, task_id: int) -> CookieSyncTask:
        row = session.execute(
            select(CookieSyncTask).where(CookieSyncTask.id == task_id)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("Cookie 采集任务不存在", "COOKIE_SYNC_TASK_NOT_FOUND", status_code=404)
        return row

    def _status_for_log(self, row: CookieSyncTask) -> str:
        return row.last_run_status or row.status or "FAIL"

    def _validate_payload(self, payload: dict[str, object], is_create: bool) -> None:
        if is_create:
            for field in ("cookie_sync_task_name", "channel", "check_url"):
                if not payload.get(field):
                    raise AppError(f"{field} 不能为空", "INVALID_PAYLOAD")
        http_method = payload.get("http_method")
        if http_method is not None and http_method not in ALLOWED_METHODS:
            raise AppError(f"不支持的请求方法: {http_method}", "INVALID_PAYLOAD")

    @staticmethod
    def _mask_sensitive(text: str) -> str:
        """脱敏 cookie/token/手机号等（与健康检测一致，Spec §8 隐私 P0）。"""
        if not text:
            return text
        masked = text
        sensitive_keys = re.compile(
            r'(?i)("(?:cookie|set-cookie|token|access_token|refresh_token|'
            r'password|passwd|secret|api[_-]?key|authorization|captcha|sms[_-]?code|'
            r'verify[_-]?code|mobile|phone|phone_number)["\']?\s*[:=]\s*["\']?)([^"\',}\s][^"\',}]{0,80})',
        )

        def _mask_value(match: re.Match[str]) -> str:
            return f"{match.group(1)}***"

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

    def _match_rule(self, rule_json: str | None, status_code: int, body: object) -> bool:
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

    def _serialize(self, row: CookieSyncTask) -> dict[str, object]:
        return {
            "id": row.id,
            "cookie_sync_task_code": row.cookie_sync_task_code,
            "cookie_sync_task_name": row.cookie_sync_task_name,
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
            "sync_wait_timeout_seconds": row.sync_wait_timeout_seconds,
            "status": row.status,
            "last_run_status": row.last_run_status,
            "last_result_message": row.last_result_message,
            "last_checked_at": row.last_checked_at,
            "last_sync_at": row.last_sync_at,
            "sync_deadline_at": row.sync_deadline_at,
            "updated_at": row.updated_at,
        }
