import unittest

from scheduler.config import validate_task_data
from scheduler.engine import run_task


TASK = {
    "id": 1,
    "name": "example",
    "site": "example-home",
    "account": "account",
    "probe_url": "https://example.test",
    "ok_statuses": (200, 204),
    "ok_statuses_text": "200,204",
    "refresh_script": "refresher.sites.site_weibo",
}


class SchedulerTests(unittest.TestCase):
    def test_normal_status_does_not_run_refresh_script(self):
        refresh_calls = []
        recorded = []
        result = run_task(
            TASK,
            cookie_loader=lambda site, account: "session=value",
            probe_func=lambda task, cookie: 200,
            refresh_func=lambda task: refresh_calls.append(task) or True,
            record_func=lambda site, account, status: recorded.append(status),
        )
        self.assertTrue(result)
        self.assertEqual(refresh_calls, [])
        self.assertEqual(recorded, [200])

    def test_unexpected_status_runs_refresh_script(self):
        refresh_calls = []
        result = run_task(
            TASK,
            cookie_loader=lambda site, account: "session=value",
            probe_func=lambda task, cookie: 302,
            refresh_func=lambda task: refresh_calls.append(task["name"]) or True,
            record_func=lambda site, account, status: None,
        )
        self.assertTrue(result)
        self.assertEqual(refresh_calls, ["example"])

    def test_missing_cookie_runs_refresh_script_without_probe(self):
        probe_calls = []
        refresh_calls = []
        result = run_task(
            TASK,
            cookie_loader=lambda site, account: None,
            probe_func=lambda task, cookie: probe_calls.append(cookie) or 200,
            refresh_func=lambda task: refresh_calls.append(task["name"]) or True,
            record_func=lambda site, account, status: None,
        )
        self.assertTrue(result)
        self.assertEqual(probe_calls, [])
        self.assertEqual(refresh_calls, ["example"])

    def test_task_validation_accepts_existing_site_script(self):
        data = {
            "name": "微博账号",
            "site": "weibo-home",
            "account": "weibo-01",
            "probe_url": "https://weibo.com",
            "ok_statuses_text": "200,204",
            "timeout_seconds": 15,
            "cdp_port": 9222,
            "refresh_script": "refresher.sites.site_weibo",
        }
        self.assertEqual(validate_task_data(data), [])

    def test_task_validation_rejects_arbitrary_module(self):
        data = {
            "name": "bad",
            "site": "bad",
            "account": "bad",
            "probe_url": "https://example.test",
            "ok_statuses_text": "200",
            "timeout_seconds": 15,
            "cdp_port": 9222,
            "refresh_script": "os",
        }
        self.assertIn(
            "刷新脚本只能使用 refresher.sites.site_xxx 格式",
            validate_task_data(data),
        )


if __name__ == "__main__":
    unittest.main()

