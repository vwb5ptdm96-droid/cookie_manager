from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import create_session_factory, create_sqlalchemy_engine
from app.core.errors import AppError


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    runtime_root = settings.runtime_root
    runtime_root.mkdir(parents=True, exist_ok=True)
    return create_sqlalchemy_engine(settings.database_url)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_engine())


def get_runtime_root(request: Request) -> Path:
    runtime_root = getattr(request.app.state, "runtime_root", get_settings().runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    return runtime_root


def require_cookie_sync_key(request: Request) -> None:
    """扩展接口 X-API-Key 鉴权。

    `COOKIE_SYNC_API_KEY` 留空时关闭鉴权（仅限本地联调）；配置非空时强制校验。
    """
    settings = get_settings()
    if not settings.cookie_sync_api_key:
        return
    if request.headers.get("X-API-Key") != settings.cookie_sync_api_key:
        raise AppError("未授权", "UNAUTHORIZED", status_code=401)
