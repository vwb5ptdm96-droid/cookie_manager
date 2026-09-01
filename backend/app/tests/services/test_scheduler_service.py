from unittest.mock import Mock, patch

from app.services.scheduler_service import HealthTaskScheduler


def test_health_task_scheduler_starts_and_shutdown() -> None:
    fake_scheduler = Mock()
    engine_mock = Mock()
    runtime_root_mock = Mock()

    with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=fake_scheduler):
        service = HealthTaskScheduler(engine=engine_mock, runtime_root=runtime_root_mock)
        service.start()
        service.shutdown()

    fake_scheduler.add_job.assert_called_once()
    fake_scheduler.start.assert_called_once()
    fake_scheduler.shutdown.assert_called_once_with(wait=False)


def test_cron_field_match() -> None:
    match = HealthTaskScheduler._cron_field_match

    assert match("*", 5, 0, 59) is True
    assert match("*/5", 5, 0, 59) is True
    assert match("*/5", 6, 0, 59) is False
    assert match("1,3,5", 3, 0, 6) is True
    assert match("1,3,5", 2, 0, 6) is False
    assert match("1-5", 3, 0, 6) is True
    assert match("1-5", 6, 0, 6) is False
    assert match("30", 30, 0, 59) is True
    assert match("30", 31, 0, 59) is False


def test_scan_skips_health_task_without_cron() -> None:
    """无 cron 表达式（=手动）的健康任务不被调度器自动执行（ASM-003）。"""
    engine_mock = Mock()
    runtime_root_mock = Mock()

    # 无 cron 的手动任务
    manual_task = Mock()
    manual_task.cron_expression = None
    manual_task.health_task_code = "ht_manual_only"
    manual_task.repair_cron_expression = None
    manual_task.repair_script_id = None

    # 有 cron 的定时任务（应正常调度）
    scheduled_task = Mock()
    scheduled_task.cron_expression = "0 * * * *"
    scheduled_task.health_task_code = "ht_scheduled"
    scheduled_task.repair_cron_expression = None
    scheduled_task.repair_script_id = None

    fake_session = Mock()
    fake_session.execute.return_value.scalars.return_value.all.return_value = [
        manual_task,
        scheduled_task,
    ]
    fake_session.__enter__ = Mock(return_value=fake_session)
    fake_session.__exit__ = Mock(return_value=False)

    with (
        patch("app.services.scheduler_service.Session", return_value=fake_session),
        patch("app.services.health_task_service.HealthTaskService") as svc_cls,
        patch.object(HealthTaskScheduler, "_scan_cookie_sync_tasks"),
    ):
        svc = svc_cls.return_value
        scheduler = HealthTaskScheduler(engine=engine_mock, runtime_root=runtime_root_mock)
        scheduler._scan()

    # 手动任务不被执行；定时任务因 cron 不匹配当前分钟也不执行
    svc.execute_check.assert_not_called()


def test_scan_executes_scheduled_task_on_cron_match() -> None:
    """cron 匹配当前时刻的启用任务被调度器执行；手动任务仍被跳过（ASM-003）。"""
    engine_mock = Mock()
    runtime_root_mock = Mock()

    manual_task = Mock()
    manual_task.cron_expression = None
    manual_task.health_task_code = "ht_manual_only"
    manual_task.repair_cron_expression = None
    manual_task.repair_script_id = None

    scheduled_task = Mock()
    scheduled_task.cron_expression = "* * * * *"  # 每分钟匹配
    scheduled_task.health_task_code = "ht_every_minute"
    scheduled_task.repair_cron_expression = None
    scheduled_task.repair_script_id = None

    fake_session = Mock()
    fake_session.execute.return_value.scalars.return_value.all.return_value = [
        manual_task,
        scheduled_task,
    ]
    fake_session.__enter__ = Mock(return_value=fake_session)
    fake_session.__exit__ = Mock(return_value=False)

    with (
        patch("app.services.scheduler_service.Session", return_value=fake_session),
        patch("app.services.health_task_service.HealthTaskService") as svc_cls,
        patch.object(HealthTaskScheduler, "_scan_cookie_sync_tasks"),
    ):
        svc = svc_cls.return_value
        scheduler = HealthTaskScheduler(engine=engine_mock, runtime_root=runtime_root_mock)
        scheduler._scan()

    # 定时任务被执行一次，手动任务不被执行
    svc.execute_check.assert_called_once_with("ht_every_minute")
