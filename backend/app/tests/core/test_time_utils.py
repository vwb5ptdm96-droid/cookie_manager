from datetime import datetime, timedelta, timezone

from app.core.time_utils import beijing_now, db_naive_as_beijing


def test_db_naive_utc_plus_eight():
    now = datetime(2026, 9, 21, 12, 0, 0)
    utc = datetime(2026, 9, 21, 4, 0, 0)
    converted = db_naive_as_beijing(utc, now=now)
    assert converted == datetime(2026, 9, 21, 12, 0, 0)


def test_db_naive_already_local_unchanged():
    now = datetime(2026, 9, 21, 12, 0, 0)
    local = datetime(2026, 9, 21, 11, 50, 0)
    assert db_naive_as_beijing(local, now=now) == local


def test_aware_converted_to_beijing_naive():
    now = datetime(2026, 9, 21, 12, 0, 0)
    utc = datetime(2026, 9, 21, 4, 0, 0, tzinfo=timezone.utc)
    assert db_naive_as_beijing(utc, now=now) == datetime(2026, 9, 21, 12, 0, 0)


def test_beijing_now_naive():
    stamp = beijing_now()
    assert stamp.tzinfo is None
