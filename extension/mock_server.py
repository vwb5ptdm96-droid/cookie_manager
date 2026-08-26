#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cookie 同步助手 - 本地模拟后端(用于联调,零第三方依赖)
================================================================
作用:在你自己电脑上验证「采集脚本 -> 后端 -> 扩展 -> 读Cookie -> 入库」整条链路。
真实部署时,把下面这些接口换成你后端服务的真实实现(写入你的业务数据库)即可。

⭐ 多来源(多同事)支持:
   每个同事的浏览器 = 一个"采集者",用 workerId 标识。
   采集脚本可为任务指定要采集的 worker(worker_ids),从而让：
     - 任务只派给指定的同事扩展去读、只读到那个同事浏览器里的 Cookie;
     - 不同同事的同一域名 Cookie 按 (worker_id, domain) 分开入库,互不混淆。
   之后做「Cookie 表映射」时,直接按 worker_id + domain 取即可。

运行:  python mock_server.py [端口]
默认:  端口 8000
可选:  set API_KEY=xxx 后启动,则要求请求带 X-API-Key 头

接口:
  GET  /api/ping                         健康检查
  POST /api/request                      [采集脚本] 请求同步某域名某同事的Cookie
       body: {"domains":[...], "worker_ids":["同事A","同事B"]}
             worker_ids 可省略 = 任意采集者(谁读到谁上报,按上报者归属)
  GET  /api/tasks?worker_id=xxx          [扩展轮询] 返回派给该采集者的待处理任务
  POST /api/tasks/{task_id}/report       [扩展上报] 提交读取到的Cookie,入库
       body: {"cookies":[...], "collected_at":"...", "worker_id":"同事A"}
  POST /api/cookies                      [扩展直接推送] 定时兜底/立即同步,直接入库
       body: {"domains":[...], "cookies":[...], "collected_at":"...", "worker_id":"同事A"}
  GET  /api/cookies?domain=xx&worker_id=yy  [采集脚本] 查某域名某同事的Cookie
  GET  /api/status                       查看已入库的 域名×采集者 分布与任务状态

数据文件: cookies_store.json,结构 {domain: {worker_id: [cookie,...]}}
================================================================
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
API_KEY = os.environ.get("API_KEY", "")  # 留空则不校验

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies_store.json")

_lock = threading.Lock()
_tasks = []  # [{task_id, worker, domains, status}]  worker 为 worker_id 或 "any"
_next_task_id = 1


# ---------------- 存储 ----------------
def load_store():
    """载入并归一化为 {domain: {worker_id: [cookie,...]}}。
    兼容旧格式(domain 直接是 cookie 列表)→ 迁移到 "unknown" 采集者。"""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    store = {}
    for d, v in raw.items():
        if isinstance(v, list):
            store[d] = {"unknown": v}  # 旧格式迁移
        elif isinstance(v, dict):
            store[d] = v
    return store


def save_store(store):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


# ---------------- HTTP 工具 ----------------
def _send_json(h, code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _auth_ok(h):
    if API_KEY and h.headers.get("X-API-Key") != API_KEY:
        _send_json(h, 401, {"error": "unauthorized"})
        return False
    return True


def _read_json(h):
    length = int(h.headers.get("Content-Length", 0))
    if not length:
        return {}
    try:
        return json.loads(h.rfile.read(length).decode("utf-8"))
    except Exception:
        return {}


def _store_cookies(worker_id, cookies):
    """按 (domain, worker_id) 归口入库。"""
    store = load_store()
    for c in cookies:
        d = c.get("domain", "")
        if not d:
            continue
        byw = store.setdefault(d, {})
        if isinstance(byw, list):  # 兼容旧格式
            byw = {"unknown": byw}
            store[d] = byw
        byw.setdefault(worker_id, []).append(c)
    save_store(store)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    # ---------- POST ----------
    def do_POST(self):
        global _next_task_id
        path = urlparse(self.path).path
        if not _auth_ok(self):
            return

        if path == "/api/request":
            body = _read_json(self)
            domains = body.get("domains", [])
            if not domains:
                return _send_json(self, 400, {"error": "domains 不能为空"})
            worker_ids = body.get("worker_ids") or []

            if worker_ids:
                # 定向:每个 worker 建一个任务,各自只派给对应的扩展
                created = []
                with _lock:
                    for w in worker_ids:
                        tid = f"task_{_next_task_id}"
                        _next_task_id += 1
                        t = {"task_id": tid, "worker": w,
                             "domains": domains, "status": "pending"}
                        _tasks.append(t)
                        created.append(t)
                print(f"📥 收到同步请求,定向采集者 {worker_ids}: {domains}")
                return _send_json(self, 200, {
                    "task_ids": [t["task_id"] for t in created],
                    "tasks": created,
                    "status": "pending",
                })
            else:
                # 广播:任意采集者,谁上报按谁归属
                with _lock:
                    tid = f"task_{_next_task_id}"
                    _next_task_id += 1
                    _tasks.append({"task_id": tid, "worker": "any",
                                   "domains": domains, "status": "pending"})
                print(f"📥 收到同步请求(任意采集者): {domains}")
                return _send_json(self, 200, {
                    "task_id": tid, "task_ids": [tid], "status": "pending",
                })

        if path.startswith("/api/tasks/") and path.endswith("/report"):
            parts = path.strip("/").split("/")  # ['api','tasks',task_id,'report']
            tid = parts[2]
            body = _read_json(self)
            cookies = body.get("cookies", [])
            # 归属优先级:body.worker_id > 任务定向的worker(非"any") > unknown
            wid = body.get("worker_id") or "unknown"
            if not body.get("worker_id"):
                with _lock:
                    for t in _tasks:
                        if t["task_id"] == tid and t["worker"] != "any":
                            wid = t["worker"]
                            break
            _store_cookies(wid, cookies)
            with _lock:
                for t in _tasks:
                    if t["task_id"] == tid:
                        t["status"] = "done"
            print(f"📤 任务 {tid} 完成,采集者 {wid},入库 {len(cookies)} 条 Cookie")
            return _send_json(self, 200, {
                "ok": True, "stored": len(cookies), "worker_id": wid,
            })

        if path == "/api/cookies":
            body = _read_json(self)
            cookies = body.get("cookies", [])
            wid = body.get("worker_id") or "unknown"
            _store_cookies(wid, cookies)
            print(f"📤 直接上报,采集者 {wid},入库 {len(cookies)} 条 Cookie")
            return _send_json(self, 200, {
                "ok": True, "stored": len(cookies), "worker_id": wid,
            })

        return _send_json(self, 404, {"error": "not found"})

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not _auth_ok(self):
            return

        if path == "/api/ping":
            return _send_json(self, 200, {"status": "ok"})

        if path == "/api/tasks":
            # 只返回派给这个采集者的任务(定向匹配 或 "any" 广播任务优先)
            wid = parse_qs(parsed.query).get("worker_id", [None])[0]
            with _lock:
                if wid:
                    pending = [t for t in _tasks
                               if t["status"] == "pending"
                               and (t["worker"] == "any" or t["worker"] == wid)]
                else:
                    pending = [t for t in _tasks if t["status"] == "pending"]
            return _send_json(self, 200, {"tasks": pending})

        if path == "/api/cookies":
            qs = parse_qs(parsed.query)
            domain = qs.get("domain", [None])[0]
            wid = qs.get("worker_id", [None])[0]
            store = load_store()
            if domain is None:
                return _send_json(self, 200, {"store": store})
            if wid:
                return _send_json(self, 200, {
                    "domain": domain, "worker_id": wid,
                    "cookies": store.get(domain, {}).get(wid, []),
                })
            return _send_json(self, 200, {
                "domain": domain,
                "workers": store.get(domain, {}),
            })

        if path == "/api/status":
            store = load_store()
            per_domain_worker = {
                d: {w: len(cs) for w, cs in byw.items()}
                for d, byw in store.items()
            }
            total = sum(len(cs) for byw in store.values() for cs in byw.values())
            with _lock:
                tasks = list(_tasks)
            return _send_json(self, 200, {
                "stored_domains": sorted(store.keys()),
                "stored_workers": sorted({w for byw in store.values() for w in byw}),
                "per_domain_worker": per_domain_worker,
                "stored_count": total,
                "tasks": tasks,
            })

        return _send_json(self, 404, {"error": "not found"})


if __name__ == "__main__":
    # 强制 stdout/stderr 用 UTF-8,避免日志里的 emoji/中文在 Windows 控制台或
    # 输出被重定向时因 GBK 编码崩溃(服务化/写日志场景尤其必要)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print(f"🍪 Cookie 同步助手 模拟后端")
    print(f"   监听:  http://0.0.0.0:{PORT}")
    print(f"   数据文件: {DATA_FILE}")
    print(f"   健康检查: http://127.0.0.1:{PORT}/api/ping")
    print(f"   API Key 校验: {'开启' if API_KEY else '关闭'}")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
