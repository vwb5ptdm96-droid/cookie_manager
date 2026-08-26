// 设置页逻辑
const $ = (id) => document.getElementById(id);

const DEFAULTS = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "",
  workerId: "",
  domains: "",
  pollEnabled: true,
  pollIntervalSeconds: 30,
  autoSyncEnabled: false,
  syncIntervalMinutes: 30,
};

async function load() {
  const { config } = await chrome.storage.local.get("config");
  const c = { ...DEFAULTS, ...(config || {}) };
  $("backendUrl").value = c.backendUrl;
  $("apiKey").value = c.apiKey;
  $("workerId").value = c.workerId;
  $("domains").value = c.domains;
  $("pollEnabled").checked = !!c.pollEnabled;
  $("pollIntervalSeconds").value = c.pollIntervalSeconds || 30;
  $("autoSyncEnabled").checked = !!c.autoSyncEnabled;
  $("syncIntervalMinutes").value = c.syncIntervalMinutes || 30;
  $("extId").textContent = chrome.runtime.id;
}

async function save() {
  const config = {
    backendUrl: $("backendUrl").value.trim(),
    apiKey: $("apiKey").value.trim(),
    workerId: $("workerId").value.trim(),
    domains: $("domains").value.trim(),
    pollEnabled: $("pollEnabled").checked,
    pollIntervalSeconds: Math.max(30, parseInt($("pollIntervalSeconds").value) || 30),
    autoSyncEnabled: $("autoSyncEnabled").checked,
    syncIntervalMinutes: Math.max(1, parseInt($("syncIntervalMinutes").value) || 30),
  };
  await chrome.storage.local.set({ config });
  // 通知后台重新配置定时器
  await chrome.runtime.sendMessage({ command: "reloadConfig" });
  flashMsg("✅ 已保存", "#1a7f37");
}

async function testConn() {
  const backendUrl = $("backendUrl").value.trim();
  if (!backendUrl) {
    flashMsg("请先填写后端地址", "#cf222e");
    return;
  }
  flashMsg("测试中...", "#888");
  const res = await chrome.runtime.sendMessage({
    command: "testConnection",
    backendUrl,
  });
  if (res && res.reachable) flashMsg("✅ 后端可达", "#1a7f37");
  else flashMsg("❌ 连接失败,请确认后端已启动", "#cf222e");
}

let msgTimer;
function flashMsg(text, color) {
  const el = $("saveMsg");
  el.textContent = text;
  el.style.color = color;
  clearTimeout(msgTimer);
  msgTimer = setTimeout(() => (el.textContent = ""), 4000);
}

$("saveBtn").addEventListener("click", save);
$("testBtn").addEventListener("click", testConn);

load();
