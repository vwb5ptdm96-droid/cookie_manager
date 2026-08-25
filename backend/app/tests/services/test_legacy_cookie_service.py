from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.legacy_cookie_service import LegacyCookieLookup, LegacyCookieService


def test_legacy_cookie_service_returns_row_by_composite_key(tmp_path: Path) -> None:
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
