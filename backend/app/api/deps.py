from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import create_session_factory, create_sqlalchemy_engine


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
