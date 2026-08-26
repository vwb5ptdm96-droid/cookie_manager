from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.models.cookie_sync_task import CookieSyncTask

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


class CookieSyncMappingService:
    """采集映射管理：唯一键 (worker_id, domain) 增删改查；删除依赖检查。"""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_mappings(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(CookieSyncMapping).order_by(CookieSyncMapping.created_at.desc())
            ).scalars().all()
        return [self._serialize(row) for row in rows]

    def create_mapping(self, payload: dict[str, object]) -> dict[str, object]:
        self._validate_payload(payload, is_create=True)
        row = CookieSyncMapping(
            worker_id=payload["worker_id"].strip(),
            domain=payload["domain"].strip().lower(),
            channel=payload["channel"].strip().upper(),
            shop_name=payload.get("shop_name"),
            mobile_phone=payload.get("mobile_phone"),
            dns=payload["dns"].strip(),
            remark=payload.get("remark"),
        )
        try:
            with Session(self.engine) as session:
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._serialize(row)
        except IntegrityError:
            logger.warning("重复映射 worker=%s domain=%s", row.worker_id, row.domain)
            raise AppError(
                f"该 (worker_id, domain) 映射已存在: {row.worker_id} / {row.domain}",
                "DUPLICATE_MAPPING",
                status_code=409,
            ) from None

    def update_mapping(self, mapping_id: int, payload: dict[str, object]) -> dict[str, object]:
        simple_fields = {
            "worker_id": str,
            "domain": str,
            "channel": str,
            "shop_name": (str, type(None)),
            "mobile_phone": (str, type(None)),
            "dns": str,
            "remark": (str, type(None)),
        }
        with Session(self.engine) as session:
            row = self._get_row(session, mapping_id)
            for field, expected_types in simple_fields.items():
                if field in payload:
                    value = payload[field]
                    if value is not None and not isinstance(value, expected_types):
                        raise AppError(f"{field} 类型不正确", "INVALID_PAYLOAD")
                    setattr(row, field, value.strip() if isinstance(value, str) else value)
            row.domain = (row.domain or "").strip().lower()
            row.channel = (row.channel or "").strip().upper()
            try:
                session.commit()
            except IntegrityError:
                raise AppError(
                    f"该 (worker_id, domain) 映射已存在: {row.worker_id} / {row.domain}",
                    "DUPLICATE_MAPPING",
                    status_code=409,
                ) from None
            session.refresh(row)
            return self._serialize(row)

    def delete_mapping(self, mapping_id: int) -> None:
        with Session(self.engine) as session:
            row = self._get_row(session, mapping_id)
            # Spec REQ-008：删除前检查是否有采集任务依赖该业务记录
            dependent = session.execute(
                select(CookieSyncTask.id).where(
                    CookieSyncTask.channel == row.channel,
                    CookieSyncTask.dns == row.dns,
                    ((CookieSyncTask.shop_name == row.shop_name) | (CookieSyncTask.shop_name.is_(None))),
                    ((CookieSyncTask.mobile_phone == row.mobile_phone) | (CookieSyncTask.mobile_phone.is_(None))),
                    CookieSyncTask.enabled.is_(True),
                )
            ).scalars().first()
            if dependent is not None:
                raise AppError(
                    "该映射的业务记录被启用的采集任务依赖，无法删除",
                    "MAPPING_IN_USE",
                    status_code=409,
                )
            session.delete(row)
            session.commit()

    def _get_row(self, session: Session, mapping_id: int) -> CookieSyncMapping:
        row = session.execute(
            select(CookieSyncMapping).where(CookieSyncMapping.id == mapping_id)
        ).scalar_one_or_none()
        if row is None:
            raise AppError("采集映射不存在", "MAPPING_NOT_FOUND", status_code=404)
        return row

    def _validate_payload(self, payload: dict[str, object], is_create: bool) -> None:
        if is_create:
            for field in ("worker_id", "domain", "channel", "dns"):
                if not payload.get(field):
                    raise AppError(f"{field} 不能为空", "INVALID_PAYLOAD")

    def _serialize(self, row: CookieSyncMapping) -> dict[str, object]:
        return {
            "id": row.id,
            "worker_id": row.worker_id,
            "domain": row.domain,
            "channel": row.channel,
            "shop_name": row.shop_name,
            "mobile_phone": row.mobile_phone,
            "dns": row.dns,
            "remark": row.remark,
            "last_report_at": row.last_report_at,
            "last_report_count": row.last_report_count,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
