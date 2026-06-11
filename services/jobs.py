"""In-process background execution for manual probe and refresh actions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from common.logger import setup_logger
from scheduler.engine import probe_cookie, run_refresh_script
from storage.mysql import (
    create_run,
    finish_run,
    get_cookie,
    get_task,
    record_probe,
    start_run,
)

logger = setup_logger("jobs")
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cookie-job")
running_task_ids: set[int] = set()
running_lock = Lock()


def submit_task_action(
    task_id: int,
    action: str,
    refresh_on_failure: bool = False,
) -> tuple[int | None, str]:
    if action not in {"probe", "refresh"}:
        return None, "不支持的操作"

    with running_lock:
        if task_id in running_task_ids:
            return None, "该任务正在执行，请稍后再试"
        running_task_ids.add(task_id)

    try:
        run_id = create_run(task_id, action)
    except Exception:
        with running_lock:
            running_task_ids.discard(task_id)
        raise

    executor.submit(
        execute_action,
        run_id,
        task_id,
        action,
        refresh_on_failure,
    )
    return run_id, ""


def execute_action(
    run_id: int,
    task_id: int,
    action: str,
    refresh_on_failure: bool = False,
) -> None:
    needs_refresh = False
    try:
        start_run(run_id)
        task = get_task(task_id)
        if task is None:
            finish_run(run_id, task_id, action, False, "任务不存在")
            return

        if action == "probe":
            needs_refresh = execute_probe(run_id, task)
        else:
            execute_refresh(run_id, task)
    except Exception as exc:
        logger.exception("Task %s %s failed", task_id, action)
        try:
            finish_run(
                run_id,
                task_id,
                action,
                False,
                f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Could not record failed run %s", run_id)
    finally:
        with running_lock:
            running_task_ids.discard(task_id)
        if action == "probe" and refresh_on_failure and needs_refresh:
            try:
                submit_task_action(task_id, "refresh")
            except Exception:
                logger.exception("Could not enqueue refresh for task %s", task_id)


def execute_probe(run_id: int, task: dict) -> bool:
    cookie = get_cookie(task["site"], task["account"])
    if not cookie:
        finish_run(
            run_id,
            task["id"],
            "probe",
            False,
            "数据库中没有该任务对应的 Cookie",
        )
        return True

    try:
        status = probe_cookie(task, cookie)
        record_probe(task["site"], task["account"], status)
    except Exception as exc:
        finish_run(
            run_id,
            task["id"],
            "probe",
            False,
            f"探测请求失败：{type(exc).__name__}: {exc}",
        )
        return True

    success = status in task["ok_statuses"]
    message = (
        f"探测正常，HTTP {status}"
        if success
        else f"状态码不符合预期：HTTP {status}，正常值为 {task['ok_statuses_text']}"
    )
    finish_run(
        run_id,
        task["id"],
        "probe",
        success,
        message,
        status,
    )
    return not success


def execute_refresh(run_id: int, task: dict) -> None:
    try:
        success = run_refresh_script(task)
    except Exception as exc:
        finish_run(
            run_id,
            task["id"],
            "refresh",
            False,
            f"刷新脚本异常：{type(exc).__name__}: {exc}",
        )
        return

    finish_run(
        run_id,
        task["id"],
        "refresh",
        success,
        "刷新脚本执行成功" if success else "刷新脚本返回失败",
    )
