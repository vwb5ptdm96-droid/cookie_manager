from pathlib import Path

from app.services.auto_repair_ticket_service import AutoRepairTicketService
from app.tests.services.test_cookie_sync_task_service import _create_task, _make_service


def test_no_mapping_opens_cookie_sync_ticket(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_trigger(engine, **kwargs):
        svc = AutoRepairTicketService(engine=engine)
        ticket = svc.create_or_reuse(
            channel=kwargs.get("channel") or "WEIXIN",
            shop_name=kwargs.get("shop_name"),
            issue_type=kwargs.get("issue_type") or "NO_MAPPING",
            kind="cookie_sync",
            cookie_sync_task_code=kwargs.get("cookie_sync_task_code"),
            error_message=kwargs.get("error_message"),
        )
        captured["ticket"] = ticket
        return {"dispatched": False, "reason": "test", "ticket_id": ticket["id"]}

    service, engine, _notifier = _make_service(tmp_path, monkeypatch, fake_http_status=500)
    monkeypatch.setattr("app.services.agent_repair_dispatcher.trigger_cookie_sync_repair", fake_trigger)
    task = _create_task(service)
    service.execute_check(str(task["cookie_sync_task_code"]))
    assert captured["ticket"]["kind"] == "cookie_sync"
    assert captured["ticket"]["issue_type"] == "NO_MAPPING"
    assert captured["ticket"]["ticket_code"].startswith("cst_")
