from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "runtime"
RUNTIME_SUBDIRS = ("profiles", "scripts", "artifacts", "logs", "cache")


def _resolve_relative_path(value: Path | str) -> Path:
    """相对路径按项目根目录解析为绝对路径，绝对路径原样保留。"""
    p = Path(value)
    return PROJECT_ROOT / p if not p.is_absolute() else p


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

    @field_validator("deploy_root", "runtime_root", mode="before")
    @classmethod
    def _resolve_root_path(cls, v: object) -> object:
        if v is None:
            return v
        return _resolve_relative_path(Path(v))

    @field_validator("database_url", mode="before")
    @classmethod
    def _resolve_relative_sqlite_path(cls, v: object) -> object:
        if not isinstance(v, str) or not v:
            return v
        for marker in ("sqlite+pysqlite:///", "sqlite:///"):
            if v.startswith(marker):
                raw = v[len(marker):]
                if raw and not Path(raw).is_absolute():
                    return f"{marker}{_resolve_relative_path(raw).as_posix()}"
        return v

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def ensure_runtime_dirs() -> None:
    """确保运行时目录存在。应用启动和迁移前调用，不依赖外部启动脚本。"""
    settings = get_settings()
    settings.runtime_root.mkdir(parents=True, exist_ok=True)
    for sub in RUNTIME_SUBDIRS:
        (settings.runtime_root / sub).mkdir(parents=True, exist_ok=True)


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
