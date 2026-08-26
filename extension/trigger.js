// trigger.html 的脚本:向扩展发送外部同步指令
const $ = (id) => document.getElementById(id);

// 记住上次填写的扩展 ID(本地存储,便于反复测试)
const saved = localStorage.getItem("extId");
if (saved) $("extId").value = saved;

$("trigger").addEventListener("click", () => {
  const extId = $("extId").value.trim();
  const domains = $("domains")
    .value.split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
  const result = $("result");

  if (!extId) {
    result.textContent = "请先填写扩展 ID";
    return;
  }
  localStorage.setItem("extId", extId);

  result.textContent = "发送中...";
  // 向扩展后台发送外部消息
  chrome.runtime.sendMessage(
    extId,
    { command: "sync", domains },
    (resp) => {
      if (chrome.runtime.lastError) {
        result.textContent = "错误: " + chrome.runtime.lastError.message;
        return;
      }
      result.textContent = JSON.stringify(resp, null, 2);
    }
  );
});
