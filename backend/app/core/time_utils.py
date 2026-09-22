"""北京时间与 DB naive datetime 的对齐。

SQLite CURRENT_TIMESTAMP 多为 UTC naive；业务时钟用北京 naive。
把落后约 8 小时的 naive 值视为 UTC 再 +8h，避免误判超时。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def db_naive_as_beijing(dt: datetime | None, *, now: datetime | None = None) -> datetime | None:
    if dt is None:
        return None
    clock = now or beijing_now()
    if dt.tzinfo is not None:
        return dt.astimezone(BEIJING_TZ).replace(tzinfo=None)
    lag_hours = (clock - dt).total_seconds() / 3600.0
    if 6.0 <= lag_hours <= 10.0:
        return dt + timedelta(hours=8)
    return dt
