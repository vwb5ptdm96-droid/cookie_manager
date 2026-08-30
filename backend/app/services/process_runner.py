from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import IO


@dataclass(frozen=True)
class ProcessRunResult:
    exit_code: int
    stdout_path: str
    stderr_path: str
    pid: int | None


def _pipe_writer(source: IO[str], dest: Path) -> None:
    """Read from source pipe and write to dest file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for line in source:
            f.write(line)
        source.close()


def run_process(
    *,
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    extra_env: dict[str, str] | None = None,
) -> ProcessRunResult:
    # 统一子进程环境，并强制 stdout/stderr 走 UTF-8（PYTHONIOENCODING）。
    # 中文 Windows 上 Python 脚本输出到管道时默认用 GBK，平台侧按 UTF-8
    # 读取（errors="replace"），中文日志会全部变成替换符乱码（典型：天猫
    # 脚本 run.log 的"填写账号/填写密码"行）。注入该变量后子进程输出 UTF-8，
    # 与平台读取一致。setdefault 保留调用方显式指定的值。
    env = {**subprocess.os.environ, **extra_env} if extra_env else dict(subprocess.os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")

    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    # Write stdout/stderr to files concurrently to avoid deadlock
    stdout_thread = Thread(target=_pipe_writer, args=(process.stdout, stdout_path))
    stderr_thread = Thread(target=_pipe_writer, args=(process.stderr, stderr_path))
    stdout_thread.start()
    stderr_thread.start()
    stdout_thread.join()
    stderr_thread.join()

    exit_code = process.wait()

    return ProcessRunResult(
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        pid=process.pid,
    )
