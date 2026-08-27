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

$("saveBtn").addEventListener("click", async () => {
  const backendUrl = $("backendUrl").value.trim().replace(/\/+$/, "") || "http://127.0.0.1:8081";
  // Cookie 等同登录凭证：非本机 http 地址会让明文过网，仅放行 https 或本机地址
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
  if (url.protocol === "http:" && !["localhost", "127.0.0.1"].includes(url.hostname)) {
    setStatus("⚠️ 非本机的 http 地址会让 Cookie 明文过网，请用 https 或本机地址", "fail");
    return;
  }
  const config = { backendUrl, apiKey: $("apiKey").value.trim() };
  await chrome.storage.local.set({ [STORAGE_KEY]: config });
  setStatus("✅ 已保存", "ok");
});

load();
