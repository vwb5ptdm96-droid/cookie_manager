from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "runtime"


class Settings(BaseSettings):
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_name: str = Field(default="session-maintenance-system", alias="APP_NAME")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8080, alias="APP_PORT")
    deploy_root: Path = Field(default=PROJECT_ROOT, alias="DEPLOY_ROOT")
    runtime_root: Path = Field(default=DEFAULT_RUNTIME_ROOT, alias="RUNTIME_ROOT")
    database_url: str = Field(
        default=f"sqlite+pysqlite:///{(DEFAULT_RUNTIME_ROOT / 'session_maintenance.db').as_posix()}",
        alias="DATABASE_URL",
    )
    mysql_host: str = Field(default="", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="ods", alias="MYSQL_DATABASE")
    txy_account: str = Field(default="", alias="TXY_ACCOUNT")
    txy_password: str = Field(default="", alias="TXY_PASSWORD")
    feishu_webhook_url: str = Field(default="", alias="FEISHU_WEBHOOK_URL")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def create_mysql_engine():
    """创建连接云端 MySQL 的 engine（用于 ods cookie 表等查询）。"""
    settings = get_settings()
    if not settings.mysql_host or not settings.mysql_user:
        return None
    password = quote(settings.mysql_password, safe="")
    url = (
        f"mysql+pymysql://{settings.mysql_user}:{password}"
        f"@{settings.mysql_host}:{settings.mysql_port}"
        f"/{settings.mysql_database}?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)
