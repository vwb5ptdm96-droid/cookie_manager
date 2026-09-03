from datetime import datetime

from sqlalchemy import create_engine

from app.core.database import Base
from app.services.auto_repair_ticket_service import AutoRepairTicketService


def build_service(tmp_path, cooldown_seconds: int = 1800, daily_budget: int = 6) -> AutoRepairTicketService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'tickets.db'}")
    Base.metadata.create_all(engine)
    return AutoRepairTicketService(engine=engine, cooldown_seconds=cooldown_seconds, daily_budget=daily_budget)


def base_ctx():
    return dict(channel="PDD", shop_name="卫官", cdp_port=9333, script_code="maintain_pdd",
                health_task_code="ht_001", script_run_id=42, issue_type="FAIL",
                error_message="脚本执行失败: timeout")


def test_create_new_ticket(tmp_path) -> None:
    svc = build_service(tmp_path)
    ticket = svc.create_or_reuse(**base_ctx())
    assert ticket["is_new"] is True
    assert ticket["status"] == "PENDING"
    assert ticket["ticket_code"].startswith("art_")
    assert ticket["channel"] == "PDD"
    assert ticket["shop_name"] == "卫官"
    assert ticket["cdp_port"] == 9333
    assert ticket["script_run_id"] == 42


def test_same_open_ticket_reused_and_context_updated(tmp_path) -> None:
    svc = build_service(tmp_path)
    first = svc.create_or_reuse(**base_ctx())
    # 同店再次失败（新 run、新端口、更改为 RISK）
    second = svc.create_or_reuse(channel="PDD", shop_name="卫官", cdp_port=9444,
                                 script_code="maintain_pdd", health_task_code="ht_001",
                                 script_run_id=43, issue_type="RISK",
                                 error_message="触发风控")
    assert second["is_new"] is False
    assert second["id"] == first["id"]
    assert second["cdp_port"] == 9444
    assert second["script_run_id"] == 43
    assert second["issue_type"] == "RISK"
    # 首次描述保留 + 追加 [再次失败] 新描述
    assert "脚本执行失败: timeout" in (second["error_message"] or "")
    assert "再次失败" in (second["error_message"] or "")


def test_closed_ticket_not_reused(tmp_path) -> None:
    svc = build_service(tmp_path)
    first = svc.create_or_reuse(**base_ctx())
    svc.record_result(first["id"], status="SOLVED", diagnosis="已消除弹窗")
    # 终态后再失败 → 新建，不复用
    again = svc.create_or_reuse(**base_ctx())
    assert again["is_new"] is True
    assert again["id"] != first["id"]


def test_cooldown_and_budget_throttle(tmp_path) -> None:
    svc = build_service(tmp_path, cooldown_seconds=1800, daily_budget=2)
    ticket = svc.create_or_reuse(**base_ctx())
    t0 = datetime(2026, 9, 3, 10, 0, 0)

    # 首次唤起通过
    assert svc.evaluate_dispatch(ticket["id"], now=t0)["ok"] is True
    svc.mark_dispatched(ticket["id"], now=t0)

    # 冷却期内：600s < 1800s
    r = svc.evaluate_dispatch(ticket["id"], now=datetime(2026, 9, 3, 10, 10, 0))
    assert r["ok"] is False and "冷却" in r["reason"]

    # 冷却过后可再唤起
    t1 = datetime(2026, 9, 3, 10, 31, 0)
    assert svc.evaluate_dispatch(ticket["id"], now=t1)["ok"] is True
    svc.mark_dispatched(ticket["id"], now=t1)  # dispatch_count=2 = daily_budget

    # 达当日预算（需先越过冷却：t2 距 t1 超过 1800s）
    t2 = datetime(2026, 9, 3, 11, 2, 0)
    r = svc.evaluate_dispatch(ticket["id"], now=t2)
    assert r["ok"] is False and "预算" in r["reason"]

    # 跨天重置
    t3 = datetime(2026, 9, 4, 9, 0, 0)
    r = svc.evaluate_dispatch(ticket["id"], now=t3)
    assert r["ok"] is True


def test_record_result_solved_and_need_human(tmp_path) -> None:
    svc = build_service(tmp_path)
    ticket = svc.create_or_reuse(**base_ctx())

    svc.record_result(ticket["id"], status="SOLVED", diagnosis="消除运营浮层，重跑通过")
    row = svc.get_ticket(ticket["id"])
    assert row["status"] == "SOLVED"
    assert row["diagnosis"] == "消除运营浮层，重跑通过"
    assert row["closed_at"] is not None

    # NEED_HUMAN
    t2 = svc.create_or_reuse(**base_ctx())
    svc.record_result(t2["id"], status="NEED_HUMAN", diagnosis="滑块验证，转人工")
    row = svc.get_ticket(t2["id"])
    assert row["status"] == "NEED_HUMAN"

    # 非法终态忽略
    t3 = svc.create_or_reuse(**base_ctx())
    svc.record_result(t3["id"], status="BOGUS")
    assert svc.get_ticket(t3["id"])["status"] == "PENDING"
