// popup 交互逻辑
const $ = (id) => document.getElementById(id);

function fmtTime(ts) {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("zh-CN");
}

async function refresh() {
  const res = await chrome.runtime.sendMessage({ command: "getStatus" });
  if (!res || !res.ok) {
    $("backend").textContent = "未初始化";
    return;
  }
  const { config, lastResult } = res;

  $("backend").textContent = config.backendUrl || "(未配置)";
  $("domains").textContent = config.domains || "(未配置)";
  $("poll").textContent = config.pollEnabled ? "开启" : "关闭";

  const card = $("lastResultCard");
  if (lastResult) {
    card.style.display = "";
    $("lastTime").textContent = fmtTime(lastResult.time);
    const detail = $("lastDetail");
    if (lastResult.ok) {
      detail.textContent = `✅ 同步 ${lastResult.count} 条 Cookie`;
      detail.className = "ok";
    } else {
      detail.textContent = `❌ ${lastResult.error || "失败"}`;
      detail.className = "fail";
    }
  } else {
    card.style.display = "none";
  }
}

$("syncBtn").addEventListener("click", async () => {
  $("statusLine").textContent = "同步中...";
  const res = await chrome.runtime.sendMessage({ command: "syncNow" });
  if (res && res.ok) {
    $("statusLine").textContent = `✅ 已上传 ${res.count} 个 Cookie`;
  } else {
    $("statusLine").textContent = `❌ ${(res && res.error) || "未知错误"}`;
  }
  refresh();
});

$("optionsBtn").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

refresh();
