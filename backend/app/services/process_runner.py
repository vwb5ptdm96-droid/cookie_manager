from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread
from typing import Callable, IO


@dataclass(frozen=True)
class ProcessRunResult:
    exit_code: int
    stdout_path: str
    stderr_path: str
    pid: int | None
    timed_out: bool = field(default=False)


def _pipe_writer(source: IO[str], dest: Path) -> None:
    """Read from source pipe and write to dest file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for line in source:
            f.write(line)
        source.close()


def _kill_process_tree(pid: int) -> None:
    """Windows 下强杀进程树（子进程及后代）。尽力而为，失败静默。"""
    if not pid:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        pass


def run_process(
    *,
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    extra_env: dict[str, str] | None = None,
    timeout: int | None = None,
    on_start: Callable[[int], None] | None = None,
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

    # 子进程已启动：立即通知上层（写 RUNNING/pid/start_time），
    # 之后父进程无论怎样退出，DB 里都有 pid 可核对、可被回收。
    if on_start is not None:
        try:
            on_start(process.pid)
        except Exception:
            pass

    # Write stdout/stderr to files concurrently to avoid deadlock
    stdout_thread = Thread(target=_pipe_writer, args=(process.stdout, stdout_path))
    stderr_thread = Thread(target=_pipe_writer, args=(process.stderr, stderr_path))
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        # 超时：杀掉整棵进程树，再回收僵尸句柄
        _kill_process_tree(process.pid)
        exit_code = process.wait()

    stdout_thread.join()
    stderr_thread.join()

    return ProcessRunResult(
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        pid=process.pid,
        timed_out=timed_out,
    )
