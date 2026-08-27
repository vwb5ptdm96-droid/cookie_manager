// Cookie 一键上报 - popup（备用入口）：主交互在页面内悬浮球，此处仅打开设置
document.getElementById("optionsBtn").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});
