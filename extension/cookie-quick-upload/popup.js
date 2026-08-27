// Cookie 一键上报 - popup 交互逻辑（手动驱动，无任务轮询）
// 打开即抓当前标签页 Cookie；手动填四字段后提交 /api/cookies/manual。
const $ = (id) => document.getElementById(id);

const state = { cookies: [], tab: null, unsupported: false };

const DEFAULT_CONFIG = { backendUrl: "http://127.0.0.1:8081", apiKey: "" };
const STORAGE_KEY = "config";

async function getConfig() {
  const { config } = await chrome.storage.local.get(STORAGE_KEY);
  return { ...DEFAULT_CONFIG, ...(config || {}) };
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function loadCookies() {
  const tab = await getActiveTab();
  if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
    return { tab, cookies: [], unsupported: true, error: null };
  }
  let cookies = [];
  let error = null;
  try {
    cookies = await chrome.cookies.getAll({ url: tab.url });
  } catch (err) {
    error = err;
  }
  return { tab, cookies, unsupported: false, error };
}

const FETCH_TIMEOUT_MS = 15000;

async function fetchWithTimeout(url, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

function setStatus(text, cls) {
  const el = $("statusLine");
  el.textContent = text || "";
  el.className = cls || "";
}

function render() {
  const { tab, cookies, unsupported } = state;
  $("pageDomain").textContent = tab && tab.url ? new URL(tab.url).hostname : "-";
  $("cookieCount").textContent = unsupported ? "不支持(需 http/https)" : `${cookies.length} 条`;

  const list = $("cookieList");
  list.innerHTML = "";
  if (!cookies.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = unsupported ? "当前页面非 http/https，无法读取" : "未抓到 Cookie，可刷新页面重试";
    list.appendChild(empty);
    return;
  }
  // 脱敏：只展示 name 与字符数，不展示明文 value
  const names = [...new Set(cookies.map((c) => c.name))];
  names.slice(0, 30).forEach((name) => {
    const row = document.createElement("div");
    row.className = "cookie-row";
    const nameEl = document.createElement("span");
    nameEl.className = "cookie-name";
    nameEl.textContent = name;
    const lenEl = document.createElement("span");
    lenEl.className = "muted";
    lenEl.textContent = `${cookies.filter((c) => c.name === name).length} 条`;
    row.appendChild(nameEl);
    row.appendChild(lenEl);
    list.appendChild(row);
  });
  if (cookies.length > 30) {
    const more = document.createElement("div");
    more.className = "muted";
    more.textContent = `… 共 ${cookies.length} 条 Cookie（列表仅预览前 30 个名称）`;
    list.appendChild(more);
  }
}

async function refreshFromTab() {
  setStatus("正在获取当前页面 Cookie...", "muted");
  const { tab, cookies, unsupported, error } = await loadCookies();
  state.tab = tab;
  state.cookies = cookies;
  state.unsupported = unsupported;
  if (error) {
    render();
    setStatus(`读取 Cookie 失败：${error.message}`, "fail");
    return;
  }
  if (!unsupported && tab) {
    // DNS 预填当前域名（可改），避免每次都手打
    if (!$("dns").value.trim()) {
      $("dns").value = new URL(tab.url).hostname;
    }
  }
  render();
  if (unsupported) {
    setStatus("当前页面不支持读取 Cookie", "fail");
  } else if (cookies.length) {
    setStatus(`已获取 ${cookies.length} 条 Cookie`, "ok");
  } else {
    setStatus("未抓到 Cookie，可点下方刷新页面重试", "fail");
  }
}

$("submitBtn").addEventListener("click", async () => {
  const btn = $("submitBtn");
  if (btn.disabled) return;

  const channel = $("channel").value.trim();
  const shopName = $("shopName").value.trim();
  const mobilePhone = $("mobilePhone").value.trim();
  const dns = $("dns").value.trim();

  if (!channel) { setStatus("请填写渠道 channel", "fail"); return; }
  if (!dns) { setStatus("请填写 DNS", "fail"); return; }
  if (!state.cookies.length) { setStatus("当前没有可上报的 Cookie", "fail"); return; }

  btn.disabled = true;
  setStatus("上报中...", "muted");
  try {
    const config = await getConfig();
    const res = await fetchWithTimeout(`${config.backendUrl.replace(/\/+$/, "")}/api/cookies/manual`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.apiKey ? { "X-API-Key": config.apiKey } : {}),
      },
      body: JSON.stringify({
        channel,
        shop_name: shopName || null,
        mobile_phone: mobilePhone || null,
        dns,
        cookies: state.cookies,
        collected_at: new Date().toISOString(),
      }),
    });
    if (!res.ok) {
      let msg = `提交失败 (${res.status})`;
      try {
        const data = await res.json();
        msg = data.message || data.detail || msg;
      } catch (_) { /* 保留默认文案 */ }
      setStatus(msg, "fail");
      return;
    }
    const data = await res.json();
    setStatus(`✅ 已${data.is_new ? "新增" : "更新"} ${data.stored} 条 Cookie`, "ok");
  } catch (err) {
    setStatus(err && err.name === "AbortError" ? "提交超时，请检查后端地址后重试" : `提交失败：${err.message}`, "fail");
  } finally {
    btn.disabled = false;
  }
});

$("refreshBtn").addEventListener("click", async () => {
  const tab = await getActiveTab();
  if (!tab || !tab.id) { setStatus("找不到当前标签页", "fail"); return; }
  setStatus("刷新页面中，稍候自动重新获取...", "muted");
  try {
    await chrome.tabs.reload(tab.id);
  } catch (err) {
    setStatus(`刷新失败：${err.message}`, "fail");
    return;
  }
  setTimeout(refreshFromTab, 1800);
});

$("optionsBtn").addEventListener("click", () => chrome.runtime.openOptionsPage());

refreshFromTab();
