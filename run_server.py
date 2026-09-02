# -*- coding: utf-8 -*-
"""Windows 服务启动引导：alembic 迁移 + uvicorn 启动。

供 NSSM 等服务包装器在无登录会话下调用，替代手工双击 bat 的流程。

用法：
    python run_server.py

流程：
    1. chdir 到 backend 执行 alembic upgrade head（迁移失败即中止，返回非零退出码）
    2. 以 app-dir backend 拉起 uvicorn，host/port 取自 .env（config.py 自动加载）
    3. 日志走 stdout/stderr，由服务包装器（NSSM）重定向到 runtime/logs/
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PYTHON = sys.executable


def run_migrations() -> int:
    """在 backend 目录执行 alembic upgrade head，失败返回非零退出码。"""
    print("[run_server] Running alembic migrations...", flush=True)
    proc = subprocess.run(
        [PYTHON, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(BACKEND),
    )
    if proc.returncode != 0:
        print(
            f"[run_server] Migrations failed, exit code {proc.returncode}",
            flush=True,
        )
        return proc.returncode
    print("[run_server] Migrations OK.", flush=True)
    return 0


def main() -> int:
    os.chdir(str(ROOT))
    rc = run_migrations()
    if rc != 0:
        return rc

    # 让 launcher 进程能 import app.* ，等价于 --app-dir backend
    sys.path.insert(0, str(BACKEND))

    import uvicorn

    from app.core.config import get_settings

    settings = get_settings()
    print(
        f"[run_server] Starting uvicorn on {settings.app_host}:{settings.app_port} ...",
        flush=True,
    )
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        app_dir=str(BACKEND),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
