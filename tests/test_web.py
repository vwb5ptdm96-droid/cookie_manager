import unittest
from unittest.mock import patch

from web.app import create_app


SAMPLE_TASK = {
    "id": 1,
    "name": "拼多多官旗",
    "site": "pdd-home",
    "account": "pdd-official",
    "username": "account",
    "password": "password",
    "probe_url": "https://mms.pinduoduo.com",
    "method": "GET",
    "ok_statuses": (200,),
    "ok_statuses_text": "200",
    "headers": {},
    "timeout_seconds": 15,
    "refresh_script": "refresher.sites.site_pdd",
    "enabled": True,
    "browser_path": "",
    "user_data_dir": "",
    "profile_dir": "Default",
    "cdp_port": 9222,
    "login_url": "https://mms.pinduoduo.com/login/",
    "last_result": "idle",
}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_index_renders_management_ui(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cookie 管理中心".encode(), response.data)
        self.assertIn("新增任务".encode(), response.data)

    @patch("web.app.get_dashboard_stats")
    @patch("web.app.list_tasks")
    def test_task_list_api(self, list_tasks_mock, stats_mock):
        list_tasks_mock.return_value = [SAMPLE_TASK]
        stats_mock.return_value = {
            "total": 1,
            "enabled": 1,
            "disabled": 0,
            "normal": 0,
            "failed": 0,
            "running": 0,
        }
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tasks"][0]["site"], "pdd-home")

    @patch("web.app.create_task")
    def test_create_task_api(self, create_task_mock):
        create_task_mock.return_value = 9
        response = self.client.post(
            "/api/tasks",
            json={
                "name": "微博账号",
                "site": "weibo-home",
                "account": "weibo-01",
                "username": "user",
                "password": "pass",
                "probe_url": "https://weibo.com",
                "ok_statuses_text": "200",
                "timeout_seconds": 15,
                "refresh_script": "refresher.sites.site_weibo",
                "enabled": True,
                "cdp_port": 9222,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["id"], 9)

    def test_create_task_rejects_arbitrary_script(self):
        response = self.client.post(
            "/api/tasks",
            json={
                "name": "错误任务",
                "site": "bad",
                "account": "bad",
                "probe_url": "https://example.test",
                "ok_statuses_text": "200",
                "timeout_seconds": 15,
                "refresh_script": "os",
                "enabled": True,
                "cdp_port": 9222,
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

