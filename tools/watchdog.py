# -*- coding: utf-8 -*-
"""生产健康探针：后端 HTTP、SQLite 可写、RDS 端口连通，失败推飞书告警。

由计划任务 SessionBackend-Watchdog 每 5 分钟调用一次（pythonw 无窗口）。
仅依赖标准库，不依赖后端进程或 backend/.venv——后端宕机时仍能自检并告警。

退出码：0 = 全部正常；非 0 = 存在故障（已尝试推送飞书告警）。
"""
import json
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # tools/ -> 项目根


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return env
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def post_feishu(env: dict[str, str], title: str, message: str, fields: dict[str, str] | None = None) -> None:
    """复用后端 notification_service 的卡片格式，告警用红色模板。"""
    url = env.get("FEISHU_WEBHOOK_URL", "")
    if not url:
        return
    lines = [f"**{title}**", "", message]
    if fields:
        for key, value in fields.items():
            lines.append(f"{key}：{value}")
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "red"},
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "Session 生命周期管理平台 · Watchdog"}]},
            ],
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def check_http(env: dict[str, str]) -> tuple[bool, str]:
    port = int(env.get("APP_PORT", "8081"))
    url = f"http://127.0.0.1:{port}/api/health"
    # 禁用代理：HTTP_PROXY 会把 localhost 也走代理导致误判
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status == 200 and '"ok"' in body, f"HTTP {resp.status}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_sqlite(env: dict[str, str]) -> tuple[bool, str]:
    db = ROOT / "runtime" / "session_maintenance.db"
    if not db.exists():
        return False, "SQLite 文件不存在"
    try:
        with open(db, "ab"):
            pass
        return True, "SQLite 可写"
    except Exception as exc:
        return False, str(exc)


def check_mysql(env: dict[str, str]) -> tuple[bool, str]:
    host = env.get("MYSQL_HOST", "")
    if not host:
        return True, "MYSQL 未配置，跳过"
    port = int(env.get("MYSQL_PORT", "3306"))
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
        return True, f"{host}:{port} 连通"
    except Exception as exc:
        return False, f"{host}:{port} {type(exc).__name__}"


def main() -> int:
    env = load_env()
    checks = [
        ("后端", check_http(env)),
        ("SQLite", check_sqlite(env)),
        ("RDS", check_mysql(env)),
    ]
    failed = [name for name, (ok, _) in checks if not ok]
    for name, (ok, detail) in checks:
        print(f"[watchdog] {name}: {'OK' if ok else 'FAIL'} {detail}")

    if failed:
        fields = {name: detail for name, (ok, detail) in checks if not ok}
        post_feishu(env, "Session 平台健康检查失败", "以下探针未通过：", fields)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
