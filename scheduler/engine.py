"""Database-backed fixed-interval scheduler."""

import importlib
import time

import requests

from common.logger import setup_logger
from storage.mysql import get_cookie, list_tasks, record_probe

logger = setup_logger("scheduler")


def probe_cookie(task: dict, cookie: str) -> int:
    headers = dict(task.get("headers", {}))
    headers["Cookie"] = cookie
    response = requests.request(
        method=task.get("method", "GET"),
        url=task["probe_url"],
        headers=headers,
        timeout=task.get("timeout_seconds", 15),
        allow_redirects=True,
    )
    return response.status_code


def run_refresh_script(task: dict) -> bool:
    module = importlib.import_module(task["refresh_script"])
    return bool(module.refresh(task))


def run_task(
    task: dict,
    cookie_loader=get_cookie,
    probe_func=probe_cookie,
    refresh_func=run_refresh_script,
    record_func=record_probe,
) -> bool:
    cookie = cookie_loader(task["site"], task["account"])
    if not cookie:
        logger.warning("[%s] Cookie missing; running refresh script", task["name"])
        return refresh_func(task)

    try:
        status = probe_func(task, cookie)
        record_func(task["site"], task["account"], status)
    except Exception as exc:
        logger.warning("[%s] probe failed: %s", task["name"], exc)
        status = None

    if status in task["ok_statuses"]:
        logger.info("[%s] probe status %s is normal", task["name"], status)
        return True

    logger.warning(
        "[%s] probe status %s is not in %s; running refresh script",
        task["name"],
        status,
        task["ok_statuses"],
    )
    return refresh_func(task)


def run_once(task_loader=list_tasks) -> None:
    from services.jobs import submit_task_action

    for task in task_loader(enabled_only=True):
        try:
            run_id, error = submit_task_action(
                task["id"],
                "probe",
                refresh_on_failure=True,
            )
            if error:
                logger.info("[%s] skipped: %s", task["name"], error)
            else:
                logger.info("[%s] scheduled probe submitted: %s", task["name"], run_id)
        except Exception:
            logger.exception("[%s] scheduled task failed", task["name"])


def run_forever(interval_hours: float, task_loader=list_tasks) -> None:
    interval_seconds = interval_hours * 3600
    if interval_seconds <= 0:
        raise ValueError("interval_hours must be greater than zero")

    logger.info("Scheduler started; interval %.2fh", interval_hours)
    while True:
        try:
            run_once(task_loader)
        except Exception:
            logger.exception("Scheduled round failed")
        logger.info("Round completed; sleeping %.0fs", interval_seconds)
        time.sleep(interval_seconds)
