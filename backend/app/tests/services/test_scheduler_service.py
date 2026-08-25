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
