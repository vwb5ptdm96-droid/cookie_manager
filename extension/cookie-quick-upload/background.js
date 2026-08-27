// Cookie 一键上报 - background service worker (MV3)
// content script 的 fetch 受宿主页面 CORS 限制，网络请求（上报 / 测试连接）
// 与 cookie 读取全部经此转发。
const DEFAULT_CONFIG = { backendUrl: "http://127.0.0.1:8081", apiKey: "" };
const STORAGE_KEY = "config";
const FETCH_TIMEOUT_MS = 15000;
const REFRESH_TAB_KEY = "cquRefreshTabId";

// ── Headers 捕获（chrome.debugger / CDP）──
// debugger 走 CDP 通道，能拿到完整请求头（含 Cookie 派生等受保护头，扩展 webRequest 拿不到）。
const CAPTURE_TIMEOUT_MS = 15000;
const CAPTURED_KEY = "cquCapturedHeaders";
const captureState = { tabId: null, hostname: "", requests: {}, pendingHeaders: {}, timer: null };

function sameHost(url, hostname) {
  try { return new URL(url).hostname === hostname; } catch (_) { return false; }
}

function resetCapture() {
  clearTimeout(captureState.timer);
  captureState.tabId = null;
  captureState.hostname = "";
  captureState.requests = {};
  captureState.pendingHeaders = {};
  captureState.timer = null;
}

function matchesTarget(meta) {
  if (meta.type !== "XHR" && meta.type !== "Fetch") return false;
  if (!meta.headers) return false;
  if (!captureState.hostname) return true; // 无 hostname 时不过滤（防御）
  return sameHost(meta.url, captureState.hostname);
}

function finishCapture(payload) {
  if (captureState.tabId == null) return;
  const tabId = captureState.tabId;
  chrome.debugger.detach({ tabId }).catch(() => {});
  resetCapture();
  // 结果持久化到 storage.session，供刷新后新注入的 content script 经 getCapturedHeaders 消费。
  // 双通道：sendMessage 即时投递（content 已注入时），storage 兜底（注入时序晚于捕获时）。
  chrome.storage.session.set({ [CAPTURED_KEY]: { tabId, ...payload } }).catch(() => {});
  chrome.tabs.sendMessage(tabId, { type: "headersCaptured", ...payload }).catch(() => {});
}

chrome.debugger.onDetach.addListener((source) => {
  // 外部 detach（如用户打开 F12 抢占调试）时同步清理，避免幽灵 timer/残留状态
  if (captureState.tabId != null && source.tabId === captureState.tabId) {
    resetCapture();
  }
});

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (captureState.tabId == null || source.tabId !== captureState.tabId) return;
  if (method === "Network.requestWillBeSent") {
    // extraInfo 可能先到（CDP 不保证事件顺序）：先查 pending 补 headers
    const meta = {
      type: params.type,
      url: params.request.url,
      headers: captureState.pendingHeaders[params.requestId] || null,
    };
    if (meta.headers) delete captureState.pendingHeaders[params.requestId];
    captureState.requests[params.requestId] = meta;
    if (matchesTarget(meta)) finishCapture({ ok: true, headers: meta.headers, url: meta.url });
  } else if (method === "Network.requestWillBeSentExtraInfo") {
    const meta = captureState.requests[params.requestId];
    if (meta) {
      meta.headers = params.headers;
      if (matchesTarget(meta)) finishCapture({ ok: true, headers: meta.headers, url: meta.url });
    } else {
      // extraInfo 先到：暂存 pending，待 willBeSent 到达补全
      captureState.pendingHeaders[params.requestId] = params.headers;
    }
  }
});

async function getConfig() {
  const { config } = await chrome.storage.local.get(STORAGE_KEY);
  return { ...DEFAULT_CONFIG, ...(config || {}) };
}

async function fetchWithTimeout(url, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "getTabCookie": {
          const tab = await getActiveTab();
          if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
            return sendResponse({ ok: true, unsupported: true, cookies: [], hostname: "", url: "" });
          }
          const cookies = await chrome.cookies.getAll({ url: tab.url });
          return sendResponse({
            ok: true,
            unsupported: false,
            cookies,
            hostname: new URL(tab.url).hostname,
            url: tab.url,
          });
        }
        case "submitManual": {
          const config = await getConfig();
          const res = await fetchWithTimeout(`${config.backendUrl.replace(/\/+$/, "")}/api/cookies/manual`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(config.apiKey ? { "X-API-Key": config.apiKey } : {}),
            },
            body: JSON.stringify({
              channel: msg.channel,
              shop_name: msg.shopName || null,
              mobile_phone: msg.mobilePhone || null,
              dns: msg.dns,
              cookies: msg.cookies,
              headers: msg.headers || null,
              collected_at: new Date().toISOString(),
            }),
          });
          if (!res.ok) {
            let message = `提交失败 (${res.status})`;
            try {
              const data = await res.json();
              message = data.message || data.detail || message;
            } catch (_) { /* 保留默认文案 */ }
            return sendResponse({ ok: false, message });
          }
          const data = await res.json();
          return sendResponse({ ok: true, is_new: data.is_new, stored: data.stored });
        }
        case "testConnection": {
          const config = await getConfig();
          const res = await fetchWithTimeout(`${config.backendUrl.replace(/\/+$/, "")}/api/ping`);
          if (!res.ok) {
            return sendResponse({ ok: false, message: `后端返回 HTTP ${res.status}` });
          }
          let data;
          try { data = await res.json(); } catch (_) { data = {}; }
          return sendResponse({ ok: true, message: `后端可达：${data.status || "ok"}` });
        }
        case "reloadTab": {
          // 用 sender.tab.id 而非活动标签，确保刷新的是发起请求的 content script 所在 tab
          const tabId = sender && sender.tab ? sender.tab.id : null;
          if (tabId != null) {
            // 刷新前记录 tab id：新注入的 content script 经 checkRefreshPending 消费并自动展开抓取
            await chrome.storage.session.set({ [REFRESH_TAB_KEY]: tabId });
            await chrome.tabs.reload(tabId);
          }
          return sendResponse({ ok: true });
        }
        case "checkRefreshPending": {
          // content script 不能直接读 storage.session（untrusted context），由 background 代读；
          // 校验发起刷新的 tab 与当前注入 tab 一致，避免其他标签页误展开。
          const pending = await chrome.storage.session.get(REFRESH_TAB_KEY);
          const tabId = sender && sender.tab ? sender.tab.id : null;
          if (pending && pending[REFRESH_TAB_KEY] != null && pending[REFRESH_TAB_KEY] === tabId) {
            await chrome.storage.session.remove(REFRESH_TAB_KEY);
            return sendResponse({ ok: true, pending: true });
          }
          return sendResponse({ ok: true, pending: false });
        }
        case "captureHeaders": {
          const tabId = sender && sender.tab ? sender.tab.id : null;
          if (tabId == null) {
            return sendResponse({ ok: false, message: "找不到当前标签页" });
          }
          // 清理旧捕获（含进行中的 timer 与 attach、上次残留的捕获结果），避免重试/手动刷新误消费
          if (captureState.tabId != null) {
            try { await chrome.debugger.detach({ tabId: captureState.tabId }); } catch (_) { /* 忽略 */ }
          }
          resetCapture();
          chrome.storage.session.remove(CAPTURED_KEY).catch(() => {});
          let hostname = "";
          try {
            hostname = sender.tab && sender.tab.url ? new URL(sender.tab.url).hostname : "";
          } catch (_) {
            return sendResponse({ ok: false, message: "无法解析当前页面地址" });
          }
          try {
            await chrome.debugger.attach({ tabId }, "1.3");
          } catch (err) {
            return sendResponse({ ok: false, message: `无法启动调试：${err.message}` });
          }
          try {
            await chrome.debugger.sendCommand({ tabId }, "Network.enable", {});
          } catch (err) {
            await chrome.debugger.detach({ tabId }).catch(() => {});
            return sendResponse({ ok: false, message: `Network 启用失败：${err.message}` });
          }
          captureState.tabId = tabId;
          captureState.hostname = hostname;
          captureState.requests = {};
          captureState.pendingHeaders = {};
          captureState.timer = setTimeout(() => {
            finishCapture({ ok: false, error: "捕获超时：刷新后未捕获到同域名 XHR/Fetch 请求（仅匹配同 hostname）" });
          }, CAPTURE_TIMEOUT_MS);
          // 自动刷新页面触发请求；debugger 跨 reload 保持 attach
          await chrome.tabs.reload(tabId);
          return sendResponse({ ok: true, message: "已开始捕获，页面将自动刷新" });
        }
        case "getCapturedHeaders": {
          // content script 不能直接读 storage.session，由 background 代读并校验 tab 归属
          const stored = await chrome.storage.session.get(CAPTURED_KEY);
          const tabId = sender && sender.tab ? sender.tab.id : null;
          const rec = stored && stored[CAPTURED_KEY];
          if (rec && rec.tabId === tabId) {
            await chrome.storage.session.remove(CAPTURED_KEY);
            const { tabId: _tid, ...payload } = rec;
            return sendResponse({ ok: true, found: true, ...payload });
          }
          return sendResponse({ ok: true, found: false });
        }
        case "openOptionsPage": {
          await chrome.runtime.openOptionsPage();
          return sendResponse({ ok: true });
        }
        default:
          return sendResponse({ ok: false, message: `未知消息类型: ${msg.type}` });
      }
    } catch (err) {
      return sendResponse({ ok: false, message: err && err.message ? err.message : String(err) });
    }
  })();
  return true; // 异步 sendResponse
});
