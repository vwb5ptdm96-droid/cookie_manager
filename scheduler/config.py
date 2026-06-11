"""Validation helpers for database-backed task configuration."""

import importlib.util
import re


SCRIPT_PATTERN = re.compile(r"^refresher\.sites\.site_[A-Za-z0-9_]+$")


def validate_task_data(data: dict) -> list[str]:
    errors = []
    for field, label in (
        ("name", "任务名称"),
        ("site", "站点标识"),
        ("account", "账号标识"),
        ("probe_url", "探测网址"),
        ("refresh_script", "刷新脚本"),
    ):
        if not str(data.get(field, "")).strip():
            errors.append(f"{label}不能为空")

    statuses = str(data.get("ok_statuses_text", "200"))
    try:
        parsed = [int(value.strip()) for value in statuses.split(",") if value.strip()]
        if not parsed or any(value < 100 or value > 599 for value in parsed):
            raise ValueError
    except ValueError:
        errors.append("正常状态码必须是 100 到 599 的数字，多个值用逗号分隔")

    try:
        timeout = int(data.get("timeout_seconds", 15))
        if timeout < 1 or timeout > 300:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("请求超时必须是 1 到 300 秒")

    try:
        port = int(data.get("cdp_port", 9222))
        if port < 1 or port > 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("CDP 端口必须是 1 到 65535")

    script = str(data.get("refresh_script", "")).strip()
    if script and not SCRIPT_PATTERN.fullmatch(script):
        errors.append("刷新脚本只能使用 refresher.sites.site_xxx 格式")
    elif script and importlib.util.find_spec(script) is None:
        errors.append(f"刷新脚本不存在：{script}")

    return errors
