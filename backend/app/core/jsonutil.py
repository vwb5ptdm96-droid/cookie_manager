"""Agent / 日志路径的 JSON 编码：datetime / Path 必须能 dumps。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def json_default(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat(timespec="seconds")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")[:500]
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps(obj: Any, **kwargs: Any) -> str:
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("default", json_default)
    return json.dumps(obj, **kwargs)
