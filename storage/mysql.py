"""MySQL access functions for tasks, Cookies and run history."""

import json
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


TASK_FIELDS = (
    "name",
    "site",
    "account",
    "username",
    "password",
    "probe_url",
    "method",
    "ok_statuses",
    "headers_json",
    "timeout_seconds",
    "refresh_script",
    "enabled",
    "browser_path",
    "user_data_dir",
    "profile_dir",
    "cdp_port",
    "login_url",
)


def get_conn():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DB", "crawler"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT", "10")),
        autocommit=False,
    )


def normalize_task(row: dict | None) -> dict | None:
    if row is None:
        return None
    task = dict(row)
    raw_headers = task.get("headers_json")
    if isinstance(raw_headers, str):
        try:
            task["headers"] = json.loads(raw_headers)
        except json.JSONDecodeError:
            task["headers"] = {}
    else:
        task["headers"] = raw_headers or {}
    task["ok_statuses_text"] = str(task.get("ok_statuses", "200"))
    task["ok_statuses"] = tuple(
        int(value.strip())
        for value in str(task.get("ok_statuses", "200")).split(",")
        if value.strip()
    )
    task["enabled"] = bool(task.get("enabled"))
    return task


def list_tasks(enabled_only: bool = False) -> list[dict]:
    sql = """
        SELECT t.*,
               c.cookie IS NOT NULL AS has_cookie,
               CHAR_LENGTH(c.cookie) AS cookie_length,
               c.updated_at AS cookie_updated_at
        FROM cookie_tasks t
        LEFT JOIN crawler_cookies c
          ON c.site = t.site AND c.account = t.account
    """
    if enabled_only:
        sql += " WHERE t.enabled = 1"
    sql += " ORDER BY t.id DESC"

    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return [normalize_task(row) for row in cursor.fetchall()]


def get_task(task_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM cookie_tasks WHERE id = %s",
                (task_id,),
            )
            return normalize_task(cursor.fetchone())


def create_task(data: dict) -> int:
    values = task_values(data)
    columns = ", ".join(TASK_FIELDS)
    placeholders = ", ".join(["%s"] * len(TASK_FIELDS))
    sql = f"INSERT INTO cookie_tasks ({columns}) VALUES ({placeholders})"
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, values)
                task_id = cursor.lastrowid
            conn.commit()
            return task_id
        except Exception:
            conn.rollback()
            raise


def update_task(task_id: int, data: dict) -> bool:
    assignments = ", ".join(f"{field} = %s" for field in TASK_FIELDS)
    sql = f"UPDATE cookie_tasks SET {assignments} WHERE id = %s"
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, (*task_values(data), task_id))
            conn.commit()
            return bool(affected)
        except Exception:
            conn.rollback()
            raise


def delete_task(task_id: int) -> bool:
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(
                    "DELETE FROM cookie_tasks WHERE id = %s",
                    (task_id,),
                )
            conn.commit()
            return bool(affected)
        except Exception:
            conn.rollback()
            raise


def set_task_enabled(task_id: int, enabled: bool) -> bool:
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(
                    "UPDATE cookie_tasks SET enabled = %s WHERE id = %s",
                    (1 if enabled else 0, task_id),
                )
            conn.commit()
            return bool(affected)
        except Exception:
            conn.rollback()
            raise


def get_cookie(site: str, account: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT cookie
                FROM crawler_cookies
                WHERE site = %s AND account = %s
                LIMIT 1
                """,
                (site, account),
            )
            row = cursor.fetchone()
    return row["cookie"] if row else None


def list_cookies() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT site,
                       account,
                       CHAR_LENGTH(cookie) AS cookie_length,
                       last_status,
                       checked_at,
                       refreshed_at,
                       updated_at
                FROM crawler_cookies
                ORDER BY updated_at DESC
                """
            )
            return cursor.fetchall()


def save_cookies(items: list[tuple[str, str, str]]) -> None:
    sql = """
        INSERT INTO crawler_cookies (site, account, cookie, refreshed_at)
        VALUES (%s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            cookie = VALUES(cookie),
            refreshed_at = NOW()
    """
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.executemany(sql, items)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def record_probe(site: str, account: str, status: int) -> None:
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE crawler_cookies
                    SET last_status = %s, checked_at = NOW()
                    WHERE site = %s AND account = %s
                    """,
                    (status, site, account),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def create_run(task_id: int, action: str) -> int:
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO task_runs (task_id, action, status)
                    VALUES (%s, %s, 'queued')
                    """,
                    (task_id, action),
                )
                run_id = cursor.lastrowid
            conn.commit()
            return run_id
        except Exception:
            conn.rollback()
            raise


def start_run(run_id: int) -> None:
    execute_write(
        """
        UPDATE task_runs
        SET status = 'running', started_at = NOW()
        WHERE id = %s
        """,
        (run_id,),
    )
    execute_write(
        """
        UPDATE cookie_tasks t
        JOIN task_runs r ON r.task_id = t.id
        SET t.last_action = r.action,
            t.last_result = 'running',
            t.last_error = NULL
        WHERE r.id = %s
        """,
        (run_id,),
    )


def finish_run(
    run_id: int,
    task_id: int,
    action: str,
    success: bool,
    message: str = "",
    http_status: int | None = None,
) -> None:
    result = "success" if success else "failed"
    time_updates = []
    if action == "probe":
        time_updates.append("checked_at = NOW()")
    if action == "refresh" and success:
        time_updates.append("refreshed_at = NOW()")
    time_sql = ", ".join(time_updates)
    if time_sql:
        time_sql += ","

    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE task_runs
                    SET status = %s,
                        http_status = %s,
                        message = %s,
                        finished_at = NOW()
                    WHERE id = %s
                    """,
                    (result, http_status, message or None, run_id),
                )
                cursor.execute(
                    f"""
                    UPDATE cookie_tasks
                    SET last_action = %s,
                        last_result = %s,
                        last_status = %s,
                        last_error = %s,
                        {time_sql}
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        action,
                        result,
                        http_status,
                        None if success else message[:2000],
                        task_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_runs(task_id: int | None = None, limit: int = 50) -> list[dict]:
    sql = """
        SELECT r.*, t.name AS task_name
        FROM task_runs r
        JOIN cookie_tasks t ON t.id = r.task_id
    """
    params: list = []
    if task_id is not None:
        sql += " WHERE r.task_id = %s"
        params.append(task_id)
    sql += " ORDER BY r.id DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()


def get_dashboard_stats() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(enabled = 1) AS enabled,
                    SUM(enabled = 0) AS disabled,
                    SUM(enabled = 1 AND last_result = 'success') AS normal,
                    SUM(enabled = 1 AND last_result = 'failed') AS failed,
                    SUM(enabled = 1 AND last_result = 'running') AS running
                FROM cookie_tasks
                """
            )
            row = cursor.fetchone()
            return {
                key: int(value or 0)
                for key, value in row.items()
            }


def task_values(data: dict) -> tuple:
    headers = data.get("headers", {})
    return (
        data["name"].strip(),
        data["site"].strip(),
        data["account"].strip(),
        data.get("username", "").strip(),
        data.get("password", ""),
        data["probe_url"].strip(),
        data.get("method", "GET").upper(),
        data.get("ok_statuses_text", "200").strip(),
        json.dumps(headers, ensure_ascii=False) if headers else None,
        int(data.get("timeout_seconds", 15)),
        data["refresh_script"].strip(),
        1 if data.get("enabled", True) else 0,
        data.get("browser_path", "").strip(),
        data.get("user_data_dir", "").strip(),
        data.get("profile_dir", "Default").strip(),
        int(data.get("cdp_port", 9222)),
        data.get("login_url", "").strip(),
    )


def execute_write(sql: str, params: tuple) -> None:
    with get_conn() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
