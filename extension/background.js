// ============================================================
// Cookie 同步助手 - 后台 Service Worker (Manifest V3)
// ------------------------------------------------------------
// 三种触发方式:
//   1. 任务轮询(推荐,实现"采集脚本发请求才执行"):
//        你的采集脚本 → 后端 /api/request 入队任务
//        → 扩展定时 GET /api/tasks 发现有任务 → 读 Cookie → 上报
//   2. 外部消息(按需): 内网页面通过 chrome.runtime.sendMessage
//        给扩展发 {command:'sync'} → 立即执行(见 trigger.html)
//   3. 定时兜底: 扩展按配置周期把指定域名的 Cookie 直接推给后端
//   4. 手动: 点扩展图标 → 立即同步
// ============================================================

const DEFAULT_CONFIG = {
  backendUrl: "http://127.0.0.1:8000", // 后端服务地址(去尾斜杠)
  apiKey: "",                          // 可选;设置后上报时带 X-API-Key 头
  workerId: "",                        // 采集者编号(标识本台电脑/这位同事),用于按人归属
  domains: "",                         // 要同步的域名,逗号分隔,如 "example.com,foo.cn"
  pollEnabled: true,                   // 任务轮询开关(按需触发,推荐开启)
  pollIntervalSeconds: 30,             // 轮询间隔(秒,Chrome alarm 最小 30s)
  autoSyncEnabled: false,              // 定时兜底同步开关
  syncIntervalMinutes: 30,             // 定时同步间隔(分钟)
};

const STORAGE_KEY = "config";
const FETCH_TIMEOUT_MS = 15000;        // 请求后端超时
const MIN_POLL_SECONDS = 30;           // alarm 最小周期

// ---------- 配置读写 ----------
async function loadConfig() {
  const { config } = await chrome.storage.local.get(STORAGE_KEY);
  return { ...DEFAULT_CONFIG, ...(config || {}) };
}

async function saveConfig(config) {
  await chrome.storage.local.set({ [STORAGE_KEY]: config });
}

// ---------- 工具函数 ----------
function parseDomains(str) {
  return (str || "")
    .split(/[,，\n;]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function log(msg, level = "info") {
  const line = `[CookieSync ${new Date().toLocaleTimeString()}] ${msg}`;
  if (level === "warn") console.warn(line);
  else if (level === "error") console.error(line);
  else console.log(line);
}

// fetch + 超时
async function fetchWithTimeout(url, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

function buildHeaders(config, json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (config.apiKey) h["X-API-Key"] = config.apiKey;
  return h;
}

function baseUrl(config) {
  return config.backendUrl.replace(/\/+$/, "");
}

// ---------- 记录最近一次同步结果(供 popup 展示) ----------
async function setLastResult(result) {
  await chrome.storage.local.set({ lastResult: result });
}

// ---------- Cookie 读取 ----------
async function readCookies(domains) {
  const map = new Map(); // key: name|domain|path,天然去重
  for (const domain of domains) {
    const d = domain.trim().toLowerCase();
    if (!d) continue;
    try {
      // domain 参数会同时命中该域名及其子域名的 Cookie
      const cookies = await chrome.cookies.getAll({ domain: d });
      for (const c of cookies) {
        map.set(`${c.name}|${c.domain}|${c.path}`, c);
      }
      log(`读取 ${d}:${cookies.length} 条`);
    } catch (e) {
      log(`读取 ${d} 的 Cookie 失败: ${e.message}`, "warn");
    }
  }
  return Array.from(map.values());
}

// ---------- 上报到后端(直接推送模式) ----------
async function uploadCookies(domains, cookieList) {
  const cfg = await loadConfig();
  const url = baseUrl(cfg) + "/api/cookies";
  const resp = await fetchWithTimeout(url, {
    method: "POST",
    headers: buildHeaders(cfg),
    body: JSON.stringify({
      domains,
      cookies: cookieList,
      worker_id: cfg.workerId,
      collected_at: new Date().toISOString(),
    }),
  });
  if (!resp.ok) {
    throw new Error(`上传失败 HTTP ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

// ---------- 执行一次同步 ----------
async function runSync(domains) {
  const cfg = await loadConfig();
  if (!cfg.backendUrl) throw new Error("未配置后端地址,请在扩展设置中填写");

  const targetDomains =
    domains && domains.length ? domains : parseDomains(cfg.domains);
  if (!targetDomains.length) throw new Error("未配置要同步的域名");

  const cookies = await readCookies(targetDomains);
  const result = await uploadCookies(targetDomains, cookies);
  await setLastResult({
    ok: true,
    time: Date.now(),
    count: cookies.length,
    domains: targetDomains,
  });
  log(`同步完成: ${targetDomains.join(",")} → ${cookies.length} 条 Cookie`);
  return { ok: true, count: cookies.length, result };
}

// ---------- 任务轮询(按需触发核心) ----------
async function pollTasks() {
  const cfg = await loadConfig();
  if (!cfg.pollEnabled || !cfg.backendUrl) return;
  try {
    // 只取派给本采集者的任务(后端按 worker_id 定向过滤)
    const qs = cfg.workerId ? `?worker_id=${encodeURIComponent(cfg.workerId)}` : "";
    const resp = await fetchWithTimeout(baseUrl(cfg) + "/api/tasks" + qs, {
      headers: buildHeaders(cfg, false),
    });
    if (!resp.ok) return; // 后端不可达等,静默等待下一轮
    const data = await resp.json();
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    if (!tasks.length) return;
    log(`发现 ${tasks.length} 个待处理任务`);
    for (const task of tasks) {
      try {
        await handleTask(task);
      } catch (e) {
        log(`处理任务 ${task.task_id} 失败: ${e.message}`, "error");
      }
    }
  } catch (e) {
    // 后端暂不可达,忽略
  }
}

async function handleTask(task) {
  const cfg = await loadConfig();
  const domains =
    task.domains && task.domains.length
      ? task.domains
      : parseDomains(cfg.domains);
  const cookies = await readCookies(domains);

  const url =
    baseUrl(cfg) + `/api/tasks/${encodeURIComponent(task.task_id)}/report`;
  const resp = await fetchWithTimeout(url, {
    method: "POST",
    headers: buildHeaders(cfg),
    body: JSON.stringify({
      cookies,
      worker_id: cfg.workerId,
      collected_at: new Date().toISOString(),
    }),
  });
  if (!resp.ok) {
    throw new Error(`上报任务失败 HTTP ${resp.status}: ${await resp.text()}`);
  }
  await setLastResult({
    ok: true,
    time: Date.now(),
    count: cookies.length,
    domains,
    task_id: task.task_id,
  });
  log(`任务 ${task.task_id} 完成,上报 ${cookies.length} 条 Cookie`);
}

// ---------- 定时器管理 ----------
async function ensureAlarm() {
  const cfg = await loadConfig();
  await chrome.alarms.clearAll();
  if (cfg.pollEnabled && cfg.backendUrl) {
    const mins = Math.max(MIN_POLL_SECONDS, cfg.pollIntervalSeconds || MIN_POLL_SECONDS) / 60;
    chrome.alarms.create("poll", { periodInMinutes: mins });
  }
  if (cfg.autoSyncEnabled && cfg.backendUrl) {
    chrome.alarms.create("sync", {
      periodInMinutes: Math.max(1, cfg.syncIntervalMinutes || 30),
    });
  }
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "poll") pollTasks().catch(() => {});
  if (alarm.name === "sync") {
    runSync()
      .catch((e) => {
        setLastResult({ ok: false, time: Date.now(), error: e.message });
        log(`定时同步失败: ${e.message}`, "error");
      });
  }
});

// ---------- 消息处理 ----------

// 内部消息:来自 popup / options
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg && msg.command) {
        case "syncNow": {
          const res = await runSync(msg.domains);
          sendResponse({ ok: true, ...res });
          break;
        }
        case "getStatus": {
          const cfg = await loadConfig();
          const { lastResult } = await chrome.storage.local.get("lastResult");
          sendResponse({ ok: true, config: cfg, lastResult: lastResult || null });
          break;
        }
        case "reloadConfig": {
          await ensureAlarm();
          sendResponse({ ok: true });
          break;
        }
        case "testConnection": {
          const ok = await testConnection(msg.backendUrl);
          sendResponse({ ok, reachable: ok });
          break;
        }
        default:
          sendResponse({ ok: false, error: "unknown command" });
      }
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true; // 异步响应
});

// 外部消息:来自你内网页面的 chrome.runtime.sendMessage(扩展ID, {command:'sync'})
// 触发来源必须在本扩展 manifest 的 externally_connectable.matches 白名单内
chrome.runtime.onMessageExternal.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.command === "sync") {
    runSync(msg.domains)
      .then((res) => sendResponse({ ok: true, ...res }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }
  return false;
});

// ---------- 初始化 ----------
async function init() {
  const { config } = await chrome.storage.local.get(STORAGE_KEY);
  if (!config) await saveConfig(DEFAULT_CONFIG);
  await ensureAlarm();
  // 启动后立即轮询一次,减少首次等待
  const cfg = await loadConfig();
  if (cfg.pollEnabled && cfg.backendUrl) pollTasks().catch(() => {});
  log("后台已启动");
}

chrome.runtime.onInstalled.addListener(init);
chrome.runtime.onStartup.addListener(init);

// ---------- 连通性测试(供 options 页使用) ----------
async function testConnection(url) {
  try {
    const resp = await fetchWithTimeout(url.replace(/\/+$/, "") + "/api/ping", {
      headers: buildHeaders({ apiKey: "" }, false),
    });
    return resp.ok;
  } catch {
    return false;
  }
}
