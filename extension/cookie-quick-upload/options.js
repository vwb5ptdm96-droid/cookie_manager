// Cookie 一键上报 - options 设置页交互
const $ = (id) => document.getElementById(id);

const STORAGE_KEY = "config";

async function load() {
  const { config } = await chrome.storage.local.get(STORAGE_KEY);
  const c = config || {};
  $("backendUrl").value = c.backendUrl || "";
  $("apiKey").value = c.apiKey || "";
}

function setStatus(text, cls) {
  const status = $("status");
  status.textContent = text;
  status.className = cls || "";
}

// 可信内网地址（本机/私网）：Cookie 明文传输只在跨公网时才危险，
// 私网地址数据不出物理网络，允许 http 直连
function isTrustedHost(hostname) {
  const lower = hostname.toLowerCase();
  if (["localhost", "127.0.0.1", "::1"].includes(lower)) return true;
  // 单标签主机名（如 server01、nas）只能走 hosts/内网 DNS 解析，视为内网
  if (!lower.includes(".")) return true;
  // RFC1918 私网地址段：10/8、172.16/12、192.168/16
  const m = lower.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (m) {
    const [a, b] = m.slice(1).map(Number);
    if ([a, b, Number(m[3]), Number(m[4])].some((n) => n > 255)) return false;
    if (a === 10) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
  }
  return false;
}

$("saveBtn").addEventListener("click", async () => {
  const backendUrl = $("backendUrl").value.trim().replace(/\/+$/, "") || "http://127.0.0.1:8081";
  // Cookie 等同登录凭证：http 明文过网仅对公网地址禁止，本机/内网地址放行
  let url;
  try {
    url = new URL(backendUrl);
  } catch (_) {
    setStatus("❌ 后端地址格式不合法", "fail");
    return;
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    setStatus("❌ 仅支持 http/https 后端地址", "fail");
    return;
  }
  if (url.protocol === "http:" && !isTrustedHost(url.hostname)) {
    setStatus("⚠️ 非本机且非内网的 http 地址会让 Cookie 明文过网，请用 https、本机或内网地址", "fail");
    return;
  }
  const config = { backendUrl, apiKey: $("apiKey").value.trim() };
  await chrome.storage.local.set({ [STORAGE_KEY]: config });
  setStatus("✅ 已保存", "ok");
});

load();
