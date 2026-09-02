# -*- coding: utf-8 -*-
"""Windows 服务启动引导：alembic 迁移 + uvicorn 启动。

供交互会话计划任务（SessionBackend-Interactive）在登录会话下调用。

用法：
    python run_server.py

流程：
    1. 加载 .env 配置，配置轮转日志（runtime/logs/backend.log）
    2. chdir 到 backend 执行 alembic upgrade head（迁移失败即中止，返回非零退出码）
    3. 以 app-dir backend 拉起 uvicorn，host/port 取自 .env（config.py 自动加载）
    4. 日志由 RotatingFileHandler 写入 runtime/logs/backend.log（10MB × 5）
"""
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PYTHON = sys.executable


def setup_logging(runtime_root: Path) -> None:
    """配置轮转文件日志（runtime/logs/backend.log）并保留控制台输出。

    日志统一收敛到 runtime/logs/backend.log，按 10MB 轮转、保留 5 份，
    避免启动脚本重定向单文件无限增长。uvicorn 的日志经 propagate 进同一文件。
    """
    log_dir = Path(runtime_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 避免重复初始化时叠加 handler
    root.handlers.clear()

    file_handler = RotatingFileHandler(
        log_dir / "backend.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root.addHandler(console)

    # 访问日志刷屏，降级到 WARNING（错误仍保留）
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def run_migrations(logger: logging.Logger) -> int:
    """在 backend 目录执行 alembic upgrade head，失败返回非零退出码。"""
    logger.info("Running alembic migrations...")
    proc = subprocess.run(
        [PYTHON, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(BACKEND),
    )
    if proc.returncode != 0:
        logger.error("Migrations failed, exit code %s", proc.returncode)
        return proc.returncode
    logger.info("Migrations OK.")
    return 0


def main() -> int:
    os.chdir(str(ROOT))

    # 让 launcher 进程能 import app.* ，等价于 --app-dir backend
    sys.path.insert(0, str(BACKEND))

    from app.core.config import get_settings

    settings = get_settings()
    setup_logging(settings.runtime_root)

    logger = logging.getLogger("run_server")
    rc = run_migrations(logger)
    if rc != 0:
        return rc

    import uvicorn

    logger.info(
        "Starting uvicorn on %s:%s ...",
        settings.app_host,
        settings.app_port,
    )
    # log_config=None：不覆盖 setup_logging 已配置的 root handler，
    # uvicorn 自身日志经 propagate 进入轮转文件
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        app_dir=str(BACKEND),
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
