from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService


def _create_legacy_table(engine, table_name: str = "ods_cookie_playwright") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                create table {table_name} (
                    channel varchar(32) not null,
                    shop_name varchar(64) not null,
                    mobile_phone varchar(32) not null,
                    DNS varchar(64) not null,
                    path varchar(255),
                    cookie text,
                    headers text,
                    str_cookie text,
                    str_1 text,
                    str_2 text,
                    file varchar(64),
                    create_time text,
                    update_time text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )


def test_legacy_cookie_service_returns_row_by_composite_key(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_table(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into ods_cookie_playwright (
                    channel, shop_name, mobile_phone, DNS, str_cookie, str_1, str_2, file
                ) values (
                    :channel, :shop_name, :mobile_phone, :dns, :str_cookie, :str_1, :str_2, :file
                )
                """
            ),
            {
                "channel": "KUAISHOU",
                "shop_name": "demo-shop",
                "mobile_phone": "13800000001",
                "dns": "s.kwaixiaodian.com",
                "str_cookie": "sid=1",
                "str_1": "csrf-token",
                "str_2": "extra-token",
                "file": "profile_ks_138",
            },
        )

    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")

    result = service.get_by_lookup(
        LegacyCookieLookup(
            channel="KUAISHOU",
            shop_name="demo-shop",
            mobile_phone="13800000001",
            dns="s.kwaixiaodian.com",
        )
    )

    assert result is not None
    assert result["str_cookie"] == "sid=1"
    assert result["file"] == "profile_ks_138"


def test_upsert_inserts_new_row(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_table(engine)
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-a", mobile_phone="13900000002", dns="store.weixin.qq.com"
    )

    created = service.upsert_by_lookup(
        lookup, cookie_json='[{"name":"sid","value":"abc"}]', str_cookie="sid=abc"
    )

    assert created is True
    row = service.get_by_lookup(lookup)
    assert row is not None
    assert row["cookie"] == '[{"name":"sid","value":"abc"}]'
    assert row["str_cookie"] == "sid=abc"
    assert row["create_time"]  # 时间列被维护
    assert row["update_time"]


def test_upsert_updates_existing_row(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_table(engine)
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-a", mobile_phone="13900000002", dns="store.weixin.qq.com"
    )

    service.upsert_by_lookup(lookup, cookie_json='[{"name":"sid","value":"old"}]', str_cookie="sid=old")
    before = service.get_by_lookup(lookup)
    create_time_before = before["create_time"]
    update_time_before = before["update_time"]

    created = service.upsert_by_lookup(
        lookup,
        cookie_json='[{"name":"sid","value":"new"}]',
        str_cookie="sid=new",
        headers='{"Cookie":"sid=new"}',
    )

    assert created is False
    row = service.get_by_lookup(lookup)
    assert row is not None
    assert row["str_cookie"] == "sid=new"
    assert row["cookie"] == '[{"name":"sid","value":"new"}]'
    assert row["headers"] == '{"Cookie":"sid=new"}'
    assert row["create_time"] == create_time_before  # 更新不覆盖 create_time
    assert row["update_time"] >= update_time_before  # update_time 被刷新（秒级粒度允许相等）


def test_upsert_skips_missing_time_columns(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table ods_cookie_playwright (
                    channel varchar(32) not null,
                    shop_name varchar(64) not null,
                    mobile_phone varchar(32) not null,
                    DNS varchar(64) not null,
                    cookie text,
                    str_cookie text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-b", mobile_phone="13900000003", dns="store.weixin.qq.com"
    )

    created = service.upsert_by_lookup(lookup, cookie_json="[]", str_cookie="")

    assert created is True
    row = service.get_by_lookup(lookup)
    assert row is not None
    assert row["str_cookie"] == ""


def test_upsert_update_without_time_columns(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table ods_cookie_playwright (
                    channel varchar(32) not null,
                    shop_name varchar(64) not null,
                    mobile_phone varchar(32) not null,
                    DNS varchar(64) not null,
                    cookie text,
                    str_cookie text,
                    primary key (channel, shop_name, mobile_phone, DNS)
                )
                """
            )
        )
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-b", mobile_phone="13900000003", dns="store.weixin.qq.com"
    )

    assert service.upsert_by_lookup(lookup, cookie_json="[]", str_cookie="v1") is True
    created = service.upsert_by_lookup(lookup, cookie_json='[{"k":"v"}]', str_cookie="v2")

    assert created is False  # 缺时间列表上仍能走 update 且不报 Unknown column
    row = service.get_by_lookup(lookup)
    assert row is not None
    assert row["str_cookie"] == "v2"


def test_upsert_rejects_invalid_table_name(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_table(engine)
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-a", mobile_phone="13900000002", dns="store.weixin.qq.com"
    )

    with pytest.raises(ValueError):
        service.upsert_by_lookup(
            lookup, cookie_json="[]", str_cookie="", table_name="ods_cookie_playwright; drop table x"
        )


def test_get_rejects_invalid_table_name(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_table(engine)
    service = LegacyCookieService(engine=engine, default_table="ods_cookie_playwright")
    lookup = LegacyCookieLookup(
        channel="WEIXIN", shop_name="shop-a", mobile_phone="13900000002", dns="store.weixin.qq.com"
    )

    with pytest.raises(ValueError):
        service.get_by_lookup(lookup, table_name="ods_cookie_playwright where 1=1 --")
