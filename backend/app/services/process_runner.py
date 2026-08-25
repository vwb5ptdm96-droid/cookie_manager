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
    env = None
    if extra_env:
        env = {**subprocess.os.environ, **extra_env}

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
