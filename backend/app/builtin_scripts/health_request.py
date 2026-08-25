from __future__ import annotations

import json
from urllib import request
from urllib.error import HTTPError, URLError

from app.core.errors import AppError


def perform_health_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: object | None,
) -> dict[str, object]:
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, method=method.upper(), headers=headers, data=payload)

    try:
        with request.urlopen(req, timeout=20) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "body": _parse_json_body(raw_body),
            }
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        return {
            "status_code": exc.code,
            "body": _parse_json_body(raw_body),
        }
    except URLError as exc:
        raise AppError(f"健康检测请求失败: {exc.reason}", "HEALTH_REQUEST_FAILED") from exc


def _parse_json_body(raw_body: str) -> object:
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body
