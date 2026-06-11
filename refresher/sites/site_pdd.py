"""PDD refresh script: one login writes home and marketing Cookies."""

import subprocess
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from common.logger import setup_logger
from storage.mysql import save_cookies

logger = setup_logger("refresher.pdd")

MARKETING_URL = (
    "https://yingxiao.pinduoduo.com/mains/"
    "promotionOverview?msfrom=mms_sidenav"
)


def refresh(task: dict) -> bool:
    error = validate_task(task)
    if error:
        logger.error("[%s] %s", task["name"], error)
        return False

    process = start_browser(task)
    if process is None:
        return False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{task['cdp_port']}"
            )
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            page.goto(task["login_url"], wait_until="domcontentloaded")
            time.sleep(2)

            if "login" in page.url.lower() and not login(page, task):
                return False

            home_cookie = collect_cookie(
                context,
                "https://mms.pinduoduo.com",
            )
            if not home_cookie:
                logger.error("[%s] home Cookie is empty", task["name"])
                return False

            page.goto(MARKETING_URL, wait_until="domcontentloaded")
            time.sleep(3)
            marketing_cookie = collect_cookie(
                context,
                "https://yingxiao.pinduoduo.com",
            )
            if not marketing_cookie:
                logger.error("[%s] marketing Cookie is empty", task["name"])
                return False

            account = task["account"]
            save_cookies(
                [
                    ("pdd-home", account, home_cookie),
                    ("pdd-marketing", account, marketing_cookie),
                ]
            )
            logger.info("[%s] two PDD Cookies saved", task["name"])
            browser.close()
            return True
    except Exception:
        logger.exception("[%s] refresh failed", task["name"])
        return False
    finally:
        if process.poll() is None:
            process.kill()


def start_browser(task: dict):
    process = subprocess.Popen(
        [
            task["browser_path"],
            f"--remote-debugging-port={task['cdp_port']}",
            f"--user-data-dir={task['user_data_dir']}",
            f"--profile-directory={task['profile_dir']}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
    )

    endpoint = f"http://127.0.0.1:{task['cdp_port']}/json/version"
    for _ in range(60):
        try:
            if requests.get(endpoint, timeout=1).status_code == 200:
                return process
        except requests.RequestException:
            pass
        time.sleep(0.5)

    logger.error("[%s] CDP port did not become ready", task["name"])
    process.kill()
    return None


def login(page, task: dict) -> bool:
    if not task["username"] or not task["password"]:
        logger.error("[%s] login credentials are not configured", task["name"])
        return False

    try:
        account_login = page.get_by_text("账号登录", exact=True)
        if account_login.count():
            account_login.first.click()
            time.sleep(1)

        page.locator("#usernameId").fill(task["username"])
        page.locator('input[type="password"]').fill(task["password"])
        page.locator("button").first.click()
        page.wait_for_url(
            lambda url: "login" not in url.lower(),
            timeout=45_000,
        )
        return True
    except Exception:
        logger.exception("[%s] login did not complete", task["name"])
        return False


def collect_cookie(context, url: str) -> str:
    cookies = context.cookies(url)
    return "; ".join(
        f"{cookie['name']}={cookie['value']}"
        for cookie in cookies
        if cookie.get("name")
    )


def validate_task(task: dict) -> str:
    if not task.get("browser_path"):
        return "PDD_BROWSER_PATH is not configured"
    if not Path(task["browser_path"]).is_file():
        return f"browser executable does not exist: {task['browser_path']}"
    if not task.get("user_data_dir"):
        return "PDD_USER_DATA_DIR is not configured"
    return ""

