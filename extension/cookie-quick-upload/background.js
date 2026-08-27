// Cookie 一键上报 - background service worker (MV3)
// content script 的 fetch 受宿主页面 CORS 限制，网络请求（上报 / 测试连接）
// 与 cookie 读取全部经此转发。
const DEFAULT_CONFIG = { backendUrl: "http://127.0.0.1:8081", apiKey: "" };
const STORAGE_KEY = "config";
const FETCH_TIMEOUT_MS = 15000;
const REFRESH_TAB_KEY = "cquRefreshTabId";

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
