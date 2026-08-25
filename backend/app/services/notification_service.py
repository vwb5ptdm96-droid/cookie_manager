from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_feishu_notification(
    title: str,
    message: str,
    *,
    fields: dict[str, str] | None = None,
) -> bool:
    settings = get_settings()
    url = settings.feishu_webhook_url
    if not url:
        logger.warning("FEISHU_WEBHOOK_URL 未配置，跳过飞书通知")
        return False

    lines = [f"**{title}**", "", f"{message}"]
    if fields:
        for key, value in fields.items():
            lines.append(f"{key}：{value}")

    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"Session 生命周期管理平台 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}]},
            ],
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("StatusCode") != 0:
            logger.error("飞书通知返回异常: %s", result)
            return False
        logger.info("飞书通知发送成功: %s", title)
        return True
    except httpx.HTTPError as exc:
        logger.error("飞书通知发送失败: %s", exc)
        return False
