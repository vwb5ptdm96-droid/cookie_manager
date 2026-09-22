"""CDP 探查工具（进 git，供 Auto-Repair Agent 使用）。

用法（项目根目录，优先 backend/.venv 的 python）：

  python tools/cdp_inspector.py --port 9333 --action ping
  python tools/cdp_inspector.py --port 9333 --action inspect --screenshot runtime/artifacts/art_xxx/shot.png
  python tools/cdp_inspector.py --port 9333 --action click --selector "button.close"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or click a Chrome CDP page")
    parser.add_argument("--port", type=int, required=True, help="remote debugging port")
    parser.add_argument(
        "--action",
        choices=("ping", "inspect", "click"),
        default="inspect",
    )
    parser.add_argument("--screenshot", default="", help="PNG path for inspect")
    parser.add_argument("--selector", default="", help="CSS selector for click")
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args(argv)


def _opener():
    # 绕过系统 HTTP_PROXY，避免 localhost 被 7897 劫持
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ping_cdp(port: int, timeout: float = 2.0) -> dict:
    url = f"http://127.0.0.1:{port}/json/version"
    with _opener().open(url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
        return {"ok": resp.status == 200, "status": resp.status, "version": data}


def _connect_page(port: int, timeout: float):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=int(timeout * 1000))
    context = browser.contexts[0] if browser.contexts else None
    if context is None:
        pw.stop()
        raise RuntimeError("CDP 已连接但没有 browser context")
    page = context.pages[0] if context.pages else context.new_page()
    return pw, browser, page


_OVERLAY_JS = """() => {
  const hits = [];
  const nodes = Array.from(document.querySelectorAll(
    '[role="dialog"], [class*="modal"], [class*="mask"], [class*="overlay"], [class*="popup"], [class*="dialog"]'
  ));
  for (const el of nodes.slice(0, 20)) {
    const st = window.getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || Number(st.opacity) === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    hits.push({
      tag: el.tagName,
      id: el.id || "",
      className: String(el.className || "").slice(0, 180),
      text: (el.innerText || "").trim().slice(0, 80),
      zIndex: st.zIndex,
    });
  }
  return hits;
}"""


def inspect_page(port: int, screenshot: str, timeout: float) -> dict:
    pw, browser, page = _connect_page(port, timeout)
    try:
        info = {
            "ok": True,
            "url": page.url,
            "title": page.title(),
            "overlays": page.evaluate(_OVERLAY_JS),
        }
        if screenshot:
            path = Path(screenshot)
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=False)
            info["screenshot"] = str(path)
        return info
    finally:
        # 不得 browser.close()：connect_over_cdp 上 close 会关掉用户正在排障的 Chrome
        pw.stop()


def click_selector(port: int, selector: str, timeout: float) -> dict:
    if not selector.strip():
        raise ValueError("click 需要 --selector")
    pw, browser, page = _connect_page(port, timeout)
    try:
        page.click(selector, timeout=int(timeout * 1000))
        time.sleep(0.3)
        return {"ok": True, "url": page.url, "clicked": selector}
    finally:
        pw.stop()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "ping":
            result = ping_cdp(args.port, timeout=args.timeout)
        elif args.action == "click":
            result = click_selector(args.port, args.selector, args.timeout)
        else:
            result = inspect_page(args.port, args.screenshot, args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
