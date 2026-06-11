"""Local UI preview with mock data. Not used by production."""

from datetime import datetime, timedelta
from unittest.mock import patch

from web.app import create_app


now = datetime.now()
tasks = [
    {
        "id": 1,
        "name": "拼多多官旗",
        "site": "pdd-home",
        "account": "pdd-official",
        "username": "绵绵的羊旗舰店IT",
        "password": "internal-password",
        "probe_url": "https://mms.pinduoduo.com",
        "ok_statuses": (200,),
        "ok_statuses_text": "200",
        "timeout_seconds": 15,
        "refresh_script": "refresher.sites.site_pdd",
        "enabled": True,
        "last_result": "success",
        "last_status": 200,
        "last_error": None,
        "checked_at": now - timedelta(minutes=12),
        "refreshed_at": now - timedelta(hours=8),
        "updated_at": now,
        "has_cookie": True,
        "cookie_length": 1836,
        "headers": {},
        "browser_path": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "user_data_dir": r"D:\cookie_profiles\pdd-official\User Data",
        "profile_dir": "Default",
        "cdp_port": 9222,
        "login_url": "https://mms.pinduoduo.com/login/",
    },
    {
        "id": 2,
        "name": "微博采集账号",
        "site": "weibo-home",
        "account": "weibo-01",
        "username": "crawler_weibo_01",
        "password": "internal-password",
        "probe_url": "https://weibo.com/ajax/profile/info",
        "ok_statuses": (200,),
        "ok_statuses_text": "200",
        "timeout_seconds": 15,
        "refresh_script": "refresher.sites.site_weibo",
        "enabled": True,
        "last_result": "success",
        "last_status": 200,
        "last_error": None,
        "checked_at": now - timedelta(minutes=46),
        "refreshed_at": now - timedelta(days=1),
        "updated_at": now,
        "has_cookie": True,
        "cookie_length": 924,
        "headers": {},
        "browser_path": "",
        "user_data_dir": "",
        "profile_dir": "Default",
        "cdp_port": 9222,
        "login_url": "",
    },
    {
        "id": 3,
        "name": "抖音数据中心",
        "site": "douyin-data",
        "account": "douyin-ops",
        "username": "douyin_ops",
        "password": "internal-password",
        "probe_url": "https://e.douyin.com/api/user/info",
        "ok_statuses": (200,),
        "ok_statuses_text": "200",
        "timeout_seconds": 15,
        "refresh_script": "refresher.sites.site_weibo",
        "enabled": True,
        "last_result": "failed",
        "last_status": 302,
        "last_error": "状态码不符合预期：HTTP 302",
        "checked_at": now - timedelta(minutes=3),
        "refreshed_at": now - timedelta(days=2),
        "updated_at": now,
        "has_cookie": True,
        "cookie_length": 1190,
        "headers": {},
        "browser_path": "",
        "user_data_dir": "",
        "profile_dir": "Default",
        "cdp_port": 9222,
        "login_url": "",
    },
    {
        "id": 4,
        "name": "小红书品牌号",
        "site": "xhs-brand",
        "account": "xhs-brand-01",
        "username": "xhs_brand_01",
        "password": "internal-password",
        "probe_url": "https://creator.xiaohongshu.com/api/me",
        "ok_statuses": (200,),
        "ok_statuses_text": "200",
        "timeout_seconds": 15,
        "refresh_script": "refresher.sites.site_weibo",
        "enabled": False,
        "last_result": "idle",
        "last_status": None,
        "last_error": None,
        "checked_at": now - timedelta(days=2),
        "refreshed_at": None,
        "updated_at": now,
        "has_cookie": False,
        "cookie_length": 0,
        "headers": {},
        "browser_path": "",
        "user_data_dir": "",
        "profile_dir": "Default",
        "cdp_port": 9222,
        "login_url": "",
    },
]

runs = [
    {
        "id": 1,
        "task_name": "拼多多官旗",
        "action": "probe",
        "status": "success",
        "http_status": 200,
        "message": "探测正常，HTTP 200",
        "started_at": now - timedelta(minutes=12, seconds=3),
        "finished_at": now - timedelta(minutes=12),
    },
    {
        "id": 2,
        "task_name": "抖音数据中心",
        "action": "probe",
        "status": "failed",
        "http_status": 302,
        "message": "状态码不符合预期：HTTP 302",
        "started_at": now - timedelta(minutes=3, seconds=2),
        "finished_at": now - timedelta(minutes=3),
    },
]

cookies = [
    {
        "site": "pdd-home",
        "account": "pdd-official",
        "cookie_length": 1836,
        "last_status": 200,
        "checked_at": now - timedelta(minutes=12),
        "refreshed_at": now - timedelta(hours=8),
        "updated_at": now,
    },
    {
        "site": "pdd-marketing",
        "account": "pdd-official",
        "cookie_length": 1624,
        "last_status": None,
        "checked_at": None,
        "refreshed_at": now - timedelta(hours=8),
        "updated_at": now,
    },
]


patches = [
    patch("web.app.list_tasks", return_value=tasks),
    patch(
        "web.app.get_dashboard_stats",
        return_value={
            "total": 4,
            "enabled": 3,
            "disabled": 1,
            "normal": 2,
            "failed": 1,
            "running": 0,
        },
    ),
    patch("web.app.list_runs", return_value=runs),
    patch("web.app.list_cookies", return_value=cookies),
    patch("web.app.get_task", side_effect=lambda task_id: next((t for t in tasks if t["id"] == task_id), None)),
]

for active_patch in patches:
    active_patch.start()

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False, use_reloader=False)
