from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.builtin_scripts.health_request import perform_health_request
from app.core.config import create_mysql_engine
from app.core.errors import AppError
from app.models.health_check import HealthCheckConfig
from app.models.session_task import SessionMaintenanceTask
from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService
from app.services.notification_service import send_feishu_notification
from app.services.run_log_service import RunLogService
from app.services.session_task_service import SessionTaskService


@dataclass(frozen=True)
class HealthCheckPayload:
    check_name: str
    cookie_table: str
    channel: str
    shop_name: str
    mobile_phone: str
    dns: str
    method: str
    check_url: str
    trigger_task_id: int
    request_headers: dict[str, object] | None = None
    request_body: dict[str, object] | None = None
    success_rule: dict[str, object] | None = None
    failure_rule: dict[str, object] | None = None


RequestRunner = Any
TaskExecutor = Any


class HealthCheckService:
    def __init__(
        self,
        *,
        engine: Engine,
        runtime_root,
        request_runner: RequestRunner | None = None,
        task_executor: TaskExecutor | None = None,
    ) -> None:
        self.engine = engine
        cookie_engine = create_mysql_engine() or engine
        self.legacy_cookie_service = LegacyCookieService(engine=cookie_engine)
        self.log_service = RunLogService(engine=engine)
        self.request_runner = request_runner or perform_health_request
        self.task_service = SessionTaskService(engine=engine, runtime_root=runtime_root)
        self.task_executor = task_executor or self._default_task_executor

    def list_checks(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(select(HealthCheckConfig).order_by(HealthCheckConfig.created_at.desc())).scalars().all()
            return [self._serialize(session, row) for row in rows]

    def create_check(self, payload: HealthCheckPayload) -> dict[str, object]:
        with Session(self.engine) as session:
            self._get_task(session, payload.trigger_task_id)

            row = HealthCheckConfig(
                check_code=self._build_check_code(),
                check_name=payload.check_name,
                cookie_table=payload.cookie_table,
                channel=payload.channel,
                shop_name=payload.shop_name,
                mobile_phone=payload.mobile_phone,
                dns=payload.dns,
                method=payload.method.upper(),
                check_url=payload.check_url,
                request_headers=self._dump_json(payload.request_headers),
                request_body=self._dump_json(payload.request_body),
                success_rule=self._dump_json(payload.success_rule),
                failure_rule=self._dump_json(payload.failure_rule),
                trigger_task_id=payload.trigger_task_id,
                status="PENDING",
                enabled=True,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(session, row)

    def update_check(self, check_code: str, payload: HealthCheckPayload) -> dict[str, object]:
        with Session(self.engine) as session:
            check = self._get_check(session, check_code)
            self._get_task(session, payload.trigger_task_id)

            check.check_name = payload.check_name
            check.cookie_table = payload.cookie_table
            check.channel = payload.channel
            check.shop_name = payload.shop_name
            check.mobile_phone = payload.mobile_phone
            check.dns = payload.dns
            check.method = payload.method.upper()
            check.check_url = payload.check_url
            check.request_headers = self._dump_json(payload.request_headers)
            check.request_body = self._dump_json(payload.request_body)
            check.success_rule = self._dump_json(payload.success_rule)
            check.failure_rule = self._dump_json(payload.failure_rule)
            check.trigger_task_id = payload.trigger_task_id
            if check.enabled and check.status == "DISABLED":
                check.status = "PENDING"

            session.commit()
            session.refresh(check)
            return self._serialize(session, check)

    def toggle_check(self, check_code: str, enabled: bool) -> dict[str, object]:
        with Session(self.engine) as session:
            check = self._get_check(session, check_code)
            check.enabled = enabled
            if not enabled:
                check.status = "DISABLED"
            elif check.status == "DISABLED":
                check.status = "PENDING"
            session.commit()
            session.refresh(check)
            return self._serialize(session, check)

    def execute_check(self, check_code: str, allow_trigger_task: bool = True) -> dict[str, object]:
        run_id = f"check_{uuid4().hex[:12]}"
        with Session(self.engine) as session:
            check = self._get_check(session, check_code)
            if not check.enabled:
                raise AppError("健康检测已停用，不能执行", "HEALTH_CHECK_DISABLED", status_code=409)
            try:
                legacy_record = self.legacy_cookie_service.get_by_lookup(
                    LegacyCookieLookup(
                        channel=check.channel,
                        shop_name=check.shop_name,
                        mobile_phone=check.mobile_phone,
                        dns=check.dns,
                    ),
                    table_name=check.cookie_table,
                )
            except SQLAlchemyError as exc:
                raise AppError(
                    f"旧 cookie 表查询失败 ({check.cookie_table}): {exc}",
                    "LEGACY_COOKIE_QUERY_FAILED",
                    status_code=422,
                ) from exc
            if legacy_record is None:
                raise AppError("旧 cookie 记录不存在", "LEGACY_COOKIE_NOT_FOUND", status_code=404)

            response = self.request_runner(
                method=check.method,
                url=check.check_url,
                headers=self._build_headers(
                    request_headers=self._load_json(check.request_headers),
                    legacy_record=legacy_record,
                ),
                body=self._build_request_body(
                    request_body=self._load_json(check.request_body),
                    legacy_record=legacy_record,
                ),
            )

            response_body = response.get("body")
            response_status = int(response.get("status_code", 0))
            body_preview = (
                json.dumps(response_body, ensure_ascii=False)
                if isinstance(response_body, (dict, list))
                else str(response_body)
            )[:50]
            failure_hit = self._match_rule(self._load_json(check.failure_rule), response_status, response_body)
            success_hit = self._match_rule(self._load_json(check.success_rule), response_status, response_body)

            triggered_task_code: str | None = None
            if failure_hit:
                check.status = "FAIL"
                check.last_result_message = "health check failed"
                self._notify_failure(check, "匹配到失败条件", body_preview)
                if check.trigger_task_id is not None and allow_trigger_task:
                    task = self._get_task(session, check.trigger_task_id)
                    task.status = "EXPIRED"
                    session.commit()
                    triggered_result = self.task_executor(task.id, task.task_code)
                    triggered_task_code = triggered_result.get("task_code") if isinstance(triggered_result, dict) else task.task_code
                else:
                    session.commit()
            elif success_hit or not self._load_json(check.success_rule):
                check.status = "PASS"
                check.last_result_message = "health check passed"
                session.commit()
            else:
                check.status = "FAIL"
                check.last_result_message = "health check did not match success rule"
                self._notify_failure(check, "未匹配到成功条件", body_preview)
                session.commit()

            check.last_checked_at = datetime.now()
            session.commit()
            session.refresh(check)

        self.log_service.write(
            run_id=run_id,
            run_type="CHECK",
            check_id=check.id,
            task_id=check.trigger_task_id,
            status=check.status,
            title=check.check_name or check.check_code,
            message=check.last_result_message or check.status,
        )

        with Session(self.engine) as session:
            check = self._get_check(session, check_code)
            payload = self._serialize(session, check)
            payload["triggered_task_code"] = triggered_task_code
            return payload

    def _notify_failure(self, check: HealthCheckConfig, reason: str, body_preview: str = "") -> None:
        try:
            fields: dict[str, str] = {
                "检测编码": check.check_code,
                "检测 URL": check.check_url,
                "请求方法": check.method,
                "当前状态": check.status,
                "结果信息": check.last_result_message or "",
            }
            if body_preview:
                fields["响应体预览"] = body_preview
            send_feishu_notification(
                title=f"健康检测失败: {check.check_name or check.check_code}",
                message=reason,
                fields=fields,
            )
        except Exception:
            logger.exception("发送飞书通知异常")

    def execute_all_checks(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            codes = [
                row.check_code
                for row in session.execute(
                    select(HealthCheckConfig).where(HealthCheckConfig.enabled.is_(True)).order_by(HealthCheckConfig.created_at.asc())
                ).scalars()
            ]
        return [self.execute_check(code) for code in codes]

    def _default_task_executor(self, task_id: int, task_code: str) -> dict[str, object]:
        return self.task_service.execute_task(task_code)

    def _get_check(self, session: Session, check_code: str) -> HealthCheckConfig:
        row = session.execute(select(HealthCheckConfig).where(HealthCheckConfig.check_code == check_code)).scalar_one_or_none()
        if row is None:
            raise AppError("健康检测不存在", "HEALTH_CHECK_NOT_FOUND", status_code=404)
        return row

    def _get_task(self, session: Session, task_id: int) -> SessionMaintenanceTask:
        row = session.execute(select(SessionMaintenanceTask).where(SessionMaintenanceTask.id == task_id)).scalar_one_or_none()
        if row is None:
            raise AppError("绑定的维护任务不存在", "TASK_NOT_FOUND", status_code=404)
        return row

    def _serialize(self, session: Session, row: HealthCheckConfig) -> dict[str, object]:
        task = self._get_task(session, row.trigger_task_id) if row.trigger_task_id is not None else None
        return {
            "id": row.id,
            "check_code": row.check_code,
            "check_name": row.check_name,
            "cookie_table": row.cookie_table,
            "channel": row.channel,
            "shop_name": row.shop_name,
            "mobile_phone": row.mobile_phone,
            "dns": row.dns,
            "method": row.method,
            "check_url": row.check_url,
            "request_headers": self._load_json(row.request_headers) or {},
            "request_body": self._load_json(row.request_body) or {},
            "success_rule": self._load_json(row.success_rule) or {},
            "failure_rule": self._load_json(row.failure_rule) or {},
            "trigger_task_id": row.trigger_task_id,
            "trigger_task_code": task.task_code if task else None,
            "status": row.status,
            "enabled": row.enabled,
            "last_result_message": row.last_result_message,
            "last_checked_at": row.last_checked_at,
            "updated_at": row.updated_at,
        }

    def _build_headers(self, *, request_headers: dict[str, object] | None, legacy_record: dict[str, object]) -> dict[str, str]:
        headers: dict[str, str] = {}
        cookie_json = legacy_record.get("cookie")
        if cookie_json:
            parsed_cookie = self._safe_json_load(cookie_json)
            if isinstance(parsed_cookie, dict):
                headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in parsed_cookie.items())

        str_cookie = legacy_record.get("str_cookie")
        if isinstance(str_cookie, str) and str_cookie.strip():
            headers["Cookie"] = str_cookie.strip()

        legacy_headers = self._safe_json_load(legacy_record.get("headers"))
        if isinstance(legacy_headers, dict):
            for key, value in legacy_headers.items():
                headers[str(key)] = str(value)

        if request_headers:
            for key, value in request_headers.items():
                headers[str(key)] = str(value)

        return headers

    def _build_request_body(self, *, request_body: dict[str, object] | None, legacy_record: dict[str, object]) -> dict[str, object] | None:
        if request_body is None:
            return None
        body = dict(request_body)
        body.setdefault("legacy_dns", legacy_record.get("DNS"))
        body.setdefault("legacy_shop_name", legacy_record.get("shop_name"))
        return body

    def _match_rule(self, rule: dict[str, object] | None, status_code: int, body: object) -> bool:
        if not rule:
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
        for part in [segment for segment in path.split(".") if segment]:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _dump_json(self, payload: dict[str, object] | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False)

    def _load_json(self, payload: str | None) -> dict[str, object] | None:
        if not payload:
            return None
        return json.loads(payload)

    def _safe_json_load(self, payload: object) -> object:
        if not isinstance(payload, str) or not payload.strip():
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def _build_check_code(self) -> str:
        return f"check_{uuid4().hex[:10]}"
