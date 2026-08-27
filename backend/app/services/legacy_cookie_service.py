from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, inspect, text

BEIJING_TZ = timezone(timedelta(hours=8))
_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def _validate_table_name(table_name: str) -> str:
    """标识符白名单校验，防止 cookie_table 等外部输入拼进 SQL。"""
    if not _TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(f"非法表名: {table_name}")
    return table_name


@dataclass(frozen=True)
class LegacyCookieLookup:
    channel: str
    shop_name: str
    mobile_phone: str
    dns: str


class LegacyCookieService:
    def __init__(self, engine: Engine, default_table: str = "ods_cookie_playwright") -> None:
        self.engine = engine
        self.default_table = default_table

    def get_by_lookup(
        self,
        lookup: LegacyCookieLookup,
        *,
        table_name: str | None = None,
    ) -> dict[str, object] | None:
        target_table = _validate_table_name(table_name or self.default_table)
        query = text(
            f"""
            select *
            from {target_table}
            where channel = :channel
              and shop_name = :shop_name
              and mobile_phone = :mobile_phone
              and DNS = :dns
            """
        )

        with self.engine.connect() as connection:
            result = connection.execute(
                query,
                {
                    "channel": lookup.channel,
                    "shop_name": lookup.shop_name,
                    "mobile_phone": lookup.mobile_phone,
                    "dns": lookup.dns,
                },
            ).mappings().first()

        return dict(result) if result is not None else None

    def upsert_by_lookup(
        self,
        lookup: LegacyCookieLookup,
        *,
        cookie_json: str,
        str_cookie: str,
        headers: str | None = None,
        table_name: str | None = None,
    ) -> bool:
        """按业务键先查后改写回旧表（Cookie 扩展采集写回用）。

        存在则更新，不存在则插入，返回是否新增。
        写回 ods 表 cookie 相关列：cookie / str_cookie / headers；
        create_time / update_time 列存在时顺带维护，缺失则跳过。
        """
        target_table = _validate_table_name(table_name or self.default_table)
        key_params: dict[str, object] = {
            "channel": lookup.channel,
            "shop_name": lookup.shop_name,
            "mobile_phone": lookup.mobile_phone,
            "dns": lookup.dns,
        }

        with self.engine.begin() as connection:
            exists = connection.execute(
                text(
                    f"select 1 from {target_table} "
                    "where channel = :channel and shop_name = :shop_name "
                    "and mobile_phone = :mobile_phone and DNS = :dns limit 1"
                ),
                key_params,
            ).first()

            columns = {c["name"] for c in inspect(connection).get_columns(target_table)}

            if exists:
                sets = ["cookie = :cookie", "str_cookie = :str_cookie"]
                params: dict[str, object] = {"cookie": cookie_json, "str_cookie": str_cookie}
                if headers is not None and "headers" in columns:
                    sets.append("headers = :headers")
                    params["headers"] = headers
                if "update_time" in columns:
                    sets.append("update_time = :now")
                    params["now"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
                params.update(key_params)
                connection.execute(
                    text(
                        f"update {target_table} set {', '.join(sets)} "
                        "where channel = :channel and shop_name = :shop_name "
                        "and mobile_phone = :mobile_phone and DNS = :dns"
                    ),
                    params,
                )
                return False

            insert_cols: list[str] = []
            insert_placeholders: list[str] = []
            insert_params: dict[str, object] = {}

            def add_col(column: str, param: str, value: object) -> None:
                insert_cols.append(column)
                insert_placeholders.append(f":{param}")
                insert_params[param] = value

            add_col("channel", "channel", lookup.channel)
            add_col("shop_name", "shop_name", lookup.shop_name)
            add_col("mobile_phone", "mobile_phone", lookup.mobile_phone)
            add_col("DNS", "dns", lookup.dns)
            add_col("cookie", "cookie", cookie_json)
            add_col("str_cookie", "str_cookie", str_cookie)
            if headers is not None and "headers" in columns:
                add_col("headers", "headers", headers)
            now_str = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
            if "create_time" in columns:
                add_col("create_time", "create_time", now_str)
            if "update_time" in columns:
                add_col("update_time", "update_time", now_str)
            connection.execute(
                text(
                    f"insert into {target_table} ({', '.join(insert_cols)}) "
                    f"values ({', '.join(insert_placeholders)})"
                ),
                insert_params,
            )
            return True
