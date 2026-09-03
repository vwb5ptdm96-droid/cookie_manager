from datetime import datetime

from sqlalchemy import create_engine

from app.core.database import Base
from app.services.auto_repair_ticket_service import AutoRepairTicketService


def build_service(tmp_path, cooldown_seconds: int = 1800, daily_budget: int = 6) -> AutoRepairTicketService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'tickets.db'}")
    Base.metadata.create_all(engine)
    return AutoRepairTicketService(engine=engine, cooldown_seconds=cooldown_seconds, daily_budget=daily_budget)


def base_ctx(**overrides):
    ctx = dict(channel="PDD", shop_name="卫官", cdp_port=9333, script_code="maintain_pdd",
               health_task_code="ht_001", script_run_id=42, issue_type="FAIL",
               error_message="脚本执行失败: timeout")
    ctx.update(overrides)
    return ctx


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


def test_shop_key_normalizes_none_and_empty(tmp_path) -> None:
    svc = build_service(tmp_path)
    # None 与空串店铺归一为同一店铺键：第二次应复用而非新建
    first = svc.create_or_reuse(channel="PDD", shop_name=None, error_message="e1")
    second = svc.create_or_reuse(channel="PDD", shop_name="", error_message="e2")
    assert first["is_new"] is True
    assert second["is_new"] is False
    assert second["id"] == first["id"]
    assert second["shop_name"] == ""


def test_same_open_ticket_reused_and_context_updated(tmp_path) -> None:
    svc = build_service(tmp_path)
    svc.create_or_reuse(**base_ctx())
    second = svc.create_or_reuse(**base_ctx(script_run_id=43, issue_type="RISK", error_message="触发风控"))
    assert second["is_new"] is False
    assert second["script_run_id"] == 43
    assert second["issue_type"] == "RISK"
    assert "再次失败" in (second["error_message"] or "")
    assert "脚本执行失败: timeout" in (second["error_message"] or "")


def test_closed_ticket_not_reused(tmp_path) -> None:
    svc = build_service(tmp_path)
    first = svc.create_or_reuse(**base_ctx())
    svc.record_result(first["id"], status="SOLVED", diagnosis="已消除弹窗")
    again = svc.create_or_reuse(**base_ctx())
    assert again["is_new"] is True
    assert again["id"] != first["id"]


def test_error_message_masked_before_persist(tmp_path) -> None:
    svc = build_service(tmp_path)
    ticket = svc.create_or_reuse(**base_ctx(error_message='cookie 异常 {"token": "secret123"} 手机号13812345678'))
    # token 值、手机号均应被脱敏
    assert "secret123" not in (ticket["error_message"] or "")
    assert "13812345678" not in (ticket["error_message"] or "")


def test_cooldown_holds_across_tickets_same_shop(tmp_path) -> None:
    """code-review P1-1 回归：节流按店铺维度，工单终态换新单不清零冷却。"""
    svc = build_service(tmp_path, cooldown_seconds=1800, daily_budget=6)
    t0 = datetime(2026, 9, 3, 10, 0, 0)

    t1 = svc.create_or_reuse(**base_ctx())
    svc.mark_dispatched(channel="PDD", shop_name="卫官", ticket_id=t1["id"], now=t0)
    svc.record_result(t1["id"], status="SOLVED", diagnosis="ok")  # 工单终态

    # 600s 后同店再失败 → 新建 PENDING 单（is_new=True），但节流仍拦（冷却未过）
    t2 = svc.create_or_reuse(**base_ctx(script_run_id=99))
    assert t2["is_new"] is True
    verdict = svc.evaluate_dispatch("PDD", "卫官", now=datetime(2026, 9, 3, 10, 10, 0))
    assert verdict["ok"] is False
    assert "冷却" in verdict["reason"]

    # 越过冷却（>1800s）后可再唤起
    verdict2 = svc.evaluate_dispatch("PDD", "卫官", now=datetime(2026, 9, 3, 10, 31, 0))
    assert verdict2["ok"] is True
    svc.mark_dispatched(channel="PDD", shop_name="卫官", ticket_id=t2["id"], now=datetime(2026, 9, 3, 10, 31, 0))


def test_daily_budget_is_shop_wide(tmp_path) -> None:
    svc = build_service(tmp_path, cooldown_seconds=0, daily_budget=2)
    t0 = datetime(2026, 9, 3, 10, 0, 0)

    a = svc.create_or_reuse(**base_ctx())
    svc.mark_dispatched(channel="PDD", shop_name="卫官", ticket_id=a["id"], now=t0)
    svc.record_result(a["id"], status="FAILED", error_message="x")
    b = svc.create_or_reuse(**base_ctx(script_run_id=2))
    svc.mark_dispatched(channel="PDD", shop_name="卫官", ticket_id=b["id"], now=t0)  # count=2
    svc.record_result(b["id"], status="SOLVED", diagnosis="ok")

    # 同店当日已达 2 次预算，即使换新单也被拦
    svc.create_or_reuse(**base_ctx(script_run_id=3))
    verdict = svc.evaluate_dispatch("PDD", "卫官", now=datetime(2026, 9, 3, 12, 0, 0))
    assert verdict["ok"] is False
    assert "预算" in verdict["reason"]

    # 跨天重置
    verdict2 = svc.evaluate_dispatch("PDD", "卫官", now=datetime(2026, 9, 4, 9, 0, 0))
    assert verdict2["ok"] is True

    # 不同店铺不受本店预算影响
    verdict3 = svc.evaluate_dispatch("PDD", "另一店", now=datetime(2026, 9, 3, 12, 0, 0))
    assert verdict3["ok"] is True


def test_record_result_statuses(tmp_path) -> None:
    svc = build_service(tmp_path)
    ticket = svc.create_or_reuse(**base_ctx())
    svc.record_result(ticket["id"], status="SOLVED", diagnosis="消除运营浮层，重跑通过")
    row = svc.get_ticket(ticket["id"])
    assert row["status"] == "SOLVED"
    assert row["diagnosis"] == "消除运营浮层，重跑通过"
    assert row["closed_at"] is not None

    t2 = svc.create_or_reuse(**base_ctx())
    svc.record_result(t2["id"], status="NEED_HUMAN", diagnosis="滑块验证，转人工")
    assert svc.get_ticket(t2["id"])["status"] == "NEED_HUMAN"

    t3 = svc.create_or_reuse(**base_ctx())
    svc.record_result(t3["id"], status="BOGUS")  # 非法终态忽略
    assert svc.get_ticket(t3["id"])["status"] == "PENDING"
