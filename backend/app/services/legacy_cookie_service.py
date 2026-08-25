from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


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
        target_table = table_name or self.default_table
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
