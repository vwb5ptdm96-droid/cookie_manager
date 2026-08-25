from __future__ import annotations

import base64
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def kill_chrome_for_profile(profile_path: Path) -> None:
    """杀掉占用指定 user-data-dir 的 Chrome 进程（包括子进程），防止缓存污染。"""
    profile_str = str(profile_path).replace("/", "\\")
    # 用 -EncodedCommand 解决中文路径编码问题
    ps_script = (
        f'Get-CimInstance Win32_Process -Filter "name=\'chrome.exe\'" | '
        f'Where-Object {{ $_.CommandLine -like \'*--user-data-dir={profile_str.replace("'", "''")}*\' }} | '
        f'Stop-Process -Force -PassThru'
    )
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode()
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            killed = [l for l in result.stdout.strip().splitlines() if l.strip()]
            if killed:
                logger.info("Chrome cleanup for %s: killed %d process(s)", profile_str, len(killed))
    except subprocess.TimeoutExpired:
        logger.warning("Chrome cleanup timed out for %s", profile_str)
    except Exception as exc:
        logger.warning("Chrome cleanup error for %s: %s", profile_str, exc)

    # Chrome 被强制杀掉后会残留 lockfile，导致下次无法启动
    for lock_file in ("lockfile", "SingletonLock", "SingletonSocket"):
        p = profile_path / lock_file
        if p.is_file():
            try:
                p.unlink()
                logger.info("Removed Chrome lockfile: %s", p)
            except Exception as exc:
                logger.warning("Failed to remove lockfile %s: %s", p, exc)


def kill_chrome_on_port(cdp_port: int) -> None:
    """通过端口号杀掉占用 CDP 端口的 Chrome 进程（兜底方案）。"""
    try:
        # netstat 找 PID
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if f":{cdp_port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1] if parts else ""
                if pid.isdigit():
                    subprocess.run(
                        ["taskkill", "-f", "-pid", pid],
                        capture_output=True, text=True, timeout=5,
                    )
                    logger.info("Killed Chrome on port %d (PID %s)", cdp_port, pid)
    except Exception as exc:
        logger.warning("Port-based Chrome cleanup failed for port %d: %s", cdp_port, exc)
