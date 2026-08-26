from __future__ import annotations

import base64
import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_DEBUG_PORT = 9222

# 常见 Chrome 安装路径探测顺序
_CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def find_chrome_executable() -> Path | None:
    """按 CHROME_PATH 或常见安装路径探测 Chrome 可执行文件，找不到返回 None。"""
    configured = (get_settings().chrome_path or "").strip()
    if configured:
        p = Path(configured)
        if p.is_file():
            return p
        logger.warning("CHROME_PATH 配置的路径不存在: %s", configured)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    for cand in (*_CHROME_CANDIDATES, str(Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe")):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def wait_for_cdp(port: int, timeout: float = 10.0) -> bool:
    """轮询 CDP 版本接口，确认端口已可调试连接。

    用显式 opener 绕开系统 HTTP_PROXY：本机部署可能配置了代理，把 localhost 请求也
    走代理会导致误判（代理返回 502 而非端口未开）。
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def launch_chrome_debug(profile_path: Path, cdp_port: int, chrome_path: Path) -> None:
    """以指定 user-data-dir + CDP 端口拉起可见 Chrome 调试窗口（脱离后端进程运行）。"""
    profile_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(chrome_path),
        f"--user-data-dir={str(profile_path)}",
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    logger.info("Launched debug Chrome for %s on port %d", profile_path, cdp_port)


def kill_chrome_for_profile(profile_path: Path) -> None:
    """杀掉占用指定 user-data-dir 的 Chrome 进程（包括子进程），防止缓存污染。"""
    profile_str = str(profile_path).replace("/", "\\")
    # 用 -EncodedCommand 解决中文路径编码问题。
    # Stop-Process 必须显式按 ProcessId 绑定：Get-CimInstance Win32_Process 返回的对象
    # 属性是 ProcessId 而非 Id，直接管道 Stop-Process 会因按 Id 绑定失败而静默不杀。
    ps_script = (
        f'Get-CimInstance Win32_Process -Filter "name=\'chrome.exe\'" | '
        f'Where-Object {{ $_.CommandLine -like \'*--user-data-dir={profile_str.replace("'", "''")}*\' }} | '
        f'ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -PassThru }}'
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


def _is_chrome_pid(pid: int) -> bool:
    """判断 PID 是否为 chrome.exe 进程（防止误杀占用端口的无关服务）。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        if not lines:
            return False
        name = lines[0].split(",")[0].strip().strip('"')
        return name.lower() == "chrome.exe"
    except Exception:
        return False


def kill_chrome_on_port(cdp_port: int) -> None:
    """通过端口号杀掉占用 CDP 端口的 Chrome 进程（兜底方案）。

    仅杀 chrome.exe，且端口精确匹配（避免子串误命中如 92225），
    防止误杀占用该端口的无关服务。
    """
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) < 5 or parts[0] != "TCP" or parts[3] != "LISTENING":
                continue
            # 本地地址形如 127.0.0.1:9222 或 [::]:9222，精确匹配端口
            local = parts[1]
            if not local.endswith(f":{cdp_port}"):
                continue
            pid = parts[-1]
            if pid.isdigit() and _is_chrome_pid(int(pid)):
                subprocess.run(
                    ["taskkill", "-f", "-pid", pid],
                    capture_output=True, text=True, timeout=5,
                )
                logger.info("Killed Chrome on port %d (PID %s)", cdp_port, pid)
    except Exception as exc:
        logger.warning("Port-based Chrome cleanup failed for port %d: %s", cdp_port, exc)
