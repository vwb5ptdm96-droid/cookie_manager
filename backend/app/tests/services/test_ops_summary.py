from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.auto_repair_ticket import AutoRepairTicket
from app.models.cookie_sync_task import CookieSyncTask
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.services.ops_summary_service import build_ops_summary


def test_ops_summary_counts_and_attention(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 20, 10, 0, 0)
    with Session(engine) as session:
        session.add(
            HealthTask(
                health_task_code="ht_fail",
                health_task_name="失败店检测",
                enabled=True,
                channel="PDD",
                shop_name="卫官",
                check_url="https://example.com",
                last_run_status="FAIL",
            )
        )
        session.add(
            CookieSyncTask(
                cookie_sync_task_code="cst_1",
                cookie_sync_task_name="采集失败",
                enabled=True,
                channel="PDD",
                shop_name="采集店",
                check_url="https://example.com",
                last_run_status="FAIL",
                status="FAIL",
            )
        )
        session.add(
            ProfileRegistry(profile_key="p1", relative_path="profiles/p1", is_locked=True)
        )
        session.add(
            AutoRepairTicket(
                ticket_code="art_need",
                channel="PDD",
                shop_name="卫官",
                status="NEED_HUMAN",
                issue_type="FAIL",
            )
        )
        session.add(
            AutoRepairTicket(
                ticket_code="art_ok",
                channel="PDD",
                shop_name="好了",
                status="SOLVED",
                issue_type="FAIL",
                closed_at=now,
            )
        )
        session.commit()

    summary = build_ops_summary(engine, now=now)
    assert summary["health"]["enabled"] == 1
    assert summary["health"]["fail"] == 1
    assert summary["cookie_sync"]["fail"] == 1
    assert summary["profiles"]["locked"] == 1
    assert summary["agent"]["need_human"] == 1
    assert summary["agent"]["solved_today"] == 1
    assert summary["attention"]
    assert summary["attention"][0]["path"] == "/auto-repair-tickets"
    assert "ticket" in summary["attention"][0]["query"]
    assert summary["as_of"].startswith("2026-09-20")
