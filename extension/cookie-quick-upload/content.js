// Cookie 一键上报 - content script：注入可拖动悬浮球 + 上报面板
// 悬浮球为主入口；cookie 读取/上报/测试连接经 background 转发（fetch 受页面 CORS 限制）。
(() => {
  if (window.__cquLoaded) return;
  window.__cquLoaded = true;

  const state = { cookies: [], hostname: "", headers: null, moved: false };

  const css = `
    #cqu-ball {
      position: fixed; right: 24px; bottom: 24px; z-index: 2147483647;
      width: 48px; height: 48px; border-radius: 50%;
      background: #2563eb; color: #fff; font-size: 22px; line-height: 48px; text-align: center;
      box-shadow: 0 2px 10px rgba(37, 99, 235, .45); cursor: grab; user-select: none;
      touch-action: none;
    }
    #cqu-ball:hover { background: #1d4ed8; }
    #cqu-ball.dragging { cursor: grabbing; }
    #cqu-panel {
      position: fixed; right: 24px; bottom: 80px; z-index: 2147483647;
      width: 320px; max-height: 80vh; overflow-y: auto;
      background: #fafafa; color: #222; border: 1px solid #e5e5e5; border-radius: 10px;
      font-family: "Microsoft YaHei", system-ui, sans-serif; font-size: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,.18); padding: 12px 14px; box-sizing: border-box;
    }
    #cqu-panel h3 { margin: 0 0 8px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
    #cqu-close { cursor: pointer; color: #888; font-size: 14px; border: none; background: none; padding: 0 2px; }
    .cqu-card { background: #fff; border: 1px solid #e5e5e5; border-radius: 8px; padding: 8px 10px; line-height: 1.7; margin-bottom: 8px; }
    .cqu-row { display: flex; justify-content: space-between; }
    .cqu-muted { color: #888; }
    .cqu-ok { color: #1a7f37; }
    .cqu-fail { color: #cf222e; }
    .cqu-label { display: block; font-size: 12px; margin: 8px 0 4px; color: #555; }
    .cqu-req::after { content: " *"; color: #cf222e; }
    #cqu-panel input { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid #d0d0d0; border-radius: 6px; font-size: 13px; }
    .cqu-btn { display: block; width: 100%; padding: 9px; margin-top: 8px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; background: #2563eb; color: #fff; }
    .cqu-btn:hover { background: #1d4ed8; }
    .cqu-btn.ghost { background: #fff; color: #2563eb; border: 1px solid #2563eb; }
    .cqu-btn:disabled { opacity: .55; cursor: not-allowed; }
    #cqu-status { font-size: 12px; min-height: 16px; margin: 8px 0 0; word-break: break-all; }
    #cqu-list { margin-top: 6px; max-height: 120px; overflow-y: auto; font-size: 12px; color: #444; }
    .cqu-item { display: flex; justify-content: space-between; border-top: 1px dashed #eee; padding: 2px 0; }
    .cqu-item-name { max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .cqu-empty { color: #888; text-align: center; padding: 6px 0; }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  (document.head || document.documentElement).appendChild(styleEl);

  const ball = document.createElement("div");
  ball.id = "cqu-ball";
  ball.title = "Cookie 一键上报";
  ball.textContent = "🍪";
  document.body.appendChild(ball);

  const panel = document.createElement("div");
  panel.id = "cqu-panel";
  panel.style.display = "none";
  panel.innerHTML = `
    <h3><span>🍪 Cookie 一键上报</span><button id="cqu-close" title="关闭">✕</button></h3>
    <div class="cqu-card">
      <div class="cqu-row"><span class="cqu-muted">当前页面</span><span id="cqu-host">-</span></div>
      <div class="cqu-row"><span class="cqu-muted">抓到 Cookie</span><span id="cqu-count">-</span></div>
      <div id="cqu-list"></div>
    </div>
    <div class="cqu-card">
      <label class="cqu-label cqu-req" for="cqu-channel">渠道 channel</label>
      <input id="cqu-channel" placeholder="如 WEIXIN / TAOBAO" />
      <label class="cqu-label" for="cqu-shop">店铺 shop_name</label>
      <input id="cqu-shop" placeholder="可空" />
      <label class="cqu-label" for="cqu-mobile">手机号 mobile_phone</label>
      <input id="cqu-mobile" placeholder="可空" />
      <label class="cqu-label cqu-req" for="cqu-dns">DNS</label>
      <input id="cqu-dns" placeholder="如 store.weixin.qq.com" />
    </div>
    <div class="cqu-card">
      <div class="cqu-row"><span class="cqu-muted">请求头</span><span id="cqu-hdr-count">未捕获</span></div>
      <div id="cqu-hdr-url" class="cqu-muted" style="word-break:break-all;"></div>
      <label class="cqu-label" for="cqu-hdr-filter">Headers 属性（可选）</label>
      <input id="cqu-hdr-filter" list="cqu-hdr-filter-options" placeholder="如 token，留空不过滤" />
      <datalist id="cqu-hdr-filter-options">
        <option value="token"></option>
      </datalist>
    </div>
    <div id="cqu-status" class="cqu-muted"></div>
    <button class="cqu-btn ghost" id="cqu-capture">抓取 Cookie + Headers（将刷新页面）</button>
    <button class="cqu-btn ghost" id="cqu-test">测试连接</button>
    <button class="cqu-btn" id="cqu-submit">上报入库</button>
    <button class="cqu-btn ghost" id="cqu-refresh">刷新页面并重新获取</button>
    <button class="cqu-btn ghost" id="cqu-options">设置</button>
  `;
  document.body.appendChild(panel);

  const el = (id) => panel.querySelector(`#${id}`);

  function setStatus(text, cls) {
    const node = el("cqu-status");
    node.textContent = text || "";
    node.className = `cqu-${cls || "muted"}`;
  }

  function renderList(cookies) {
    const list = el("cqu-list");
    list.textContent = "";
    if (!cookies.length) {
      const empty = document.createElement("div");
      empty.className = "cqu-empty";
      empty.textContent = state.hostname ? "未抓到 Cookie，可刷新页面重试" : "当前页面非 http/https，无法读取";
      list.appendChild(empty);
      return;
    }
    // 脱敏：仅展示 name 与同名字条数，value 不进 DOM
    const names = [...new Set(cookies.map((c) => c.name))];
    names.slice(0, 20).forEach((name) => {
      const row = document.createElement("div");
      row.className = "cqu-item";
      const nameEl = document.createElement("span");
      nameEl.className = "cqu-item-name";
      nameEl.textContent = name;
      const cnt = document.createElement("span");
      cnt.className = "cqu-muted";
      cnt.textContent = `${cookies.filter((c) => c.name === name).length} 条`;
      row.appendChild(nameEl);
      row.appendChild(cnt);
      list.appendChild(row);
    });
    if (cookies.length > 20) {
      const more = document.createElement("div");
      more.className = "cqu-muted";
      more.textContent = `… 共 ${cookies.length} 条 Cookie（列表仅预览前 20 个名称）`;
      list.appendChild(more);
    }
  }

  async function refreshCookies() {
    setStatus("正在获取当前页面 Cookie...");
    let res;
    try {
      res = await chrome.runtime.sendMessage({ type: "getTabCookie" });
    } catch (err) {
      setStatus(`读取失败：${err.message}`, "fail");
      return;
    }
    if (!res || !res.ok) {
      setStatus(res && res.message ? res.message : "读取失败", "fail");
      return;
    }
    state.cookies = res.cookies;
    state.hostname = res.hostname;
    el("cqu-host").textContent = res.hostname || "-";
    el("cqu-count").textContent = res.unsupported ? "不支持(需 http/https)" : `${res.cookies.length} 条`;
    renderList(res.cookies);
    if (!res.unsupported && res.hostname && !el("cqu-dns").value.trim()) {
      el("cqu-dns").value = res.hostname; // DNS 预填当前域名，可改
    }
    if (res.unsupported) {
      setStatus("当前页面不支持读取 Cookie", "fail");
    } else if (res.cookies.length) {
      setStatus(`已获取 ${res.cookies.length} 条 Cookie`, "ok");
    } else {
      setStatus("未抓到 Cookie，可刷新页面重试", "fail");
    }
  }

  function togglePanel() {
    panel.style.display = panel.style.display === "none" ? "block" : "none";
    if (panel.style.display !== "none") {
      refreshCookies();
    }
  }

  // ── 悬浮球拖动 ──
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let baseX = 0;
  let baseY = 0;

  ball.addEventListener("pointerdown", (e) => {
    dragging = true;
    state.moved = false;
    startX = e.clientX;
    startY = e.clientY;
    const rect = ball.getBoundingClientRect();
    baseX = rect.left;
    baseY = rect.top;
    ball.setPointerCapture(e.pointerId);
    ball.classList.add("dragging");
  });
  ball.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) + Math.abs(dy) > 5) state.moved = true;
    ball.style.left = Math.max(0, Math.min(window.innerWidth - 48, baseX + dx)) + "px";
    ball.style.top = Math.max(0, Math.min(window.innerHeight - 48, baseY + dy)) + "px";
  });
  ball.addEventListener("pointerup", (e) => {
    dragging = false;
    ball.classList.remove("dragging");
    try { ball.releasePointerCapture(e.pointerId); } catch (_) { /* 忽略 */ }
    if (!state.moved) togglePanel();
  });
  ball.addEventListener("pointercancel", (e) => {
    // 拖动被系统手势/OS 打断时收尾，避免状态残留
    dragging = false;
    ball.classList.remove("dragging");
    try { ball.releasePointerCapture(e.pointerId); } catch (_) { /* 忽略 */ }
  });

  // ── 面板交互 ──
  el("cqu-close").addEventListener("click", () => { panel.style.display = "none"; });

  el("cqu-capture").addEventListener("click", async () => {
    const btn = el("cqu-capture");
    const filter = el("cqu-hdr-filter").value.trim();
    btn.disabled = true;
    setStatus(filter ? `正在抓取请求头（页面将自动刷新，Headers 属性「${filter}」）...` : "正在抓取请求头（页面将自动刷新）...");
    try {
      const res = await chrome.runtime.sendMessage({ type: "captureHeaders", filter });
      if (!res || !res.ok) {
        setStatus(res && res.message ? res.message : "启动捕获失败", "fail");
        btn.disabled = false;
      }
      // 成功时页面刷新、content script 重建，结果由 background 的 headersCaptured 消息带回
    } catch (err) {
      setStatus(`启动捕获失败：${err.message}`, "fail");
      btn.disabled = false;
    }
  });

  el("cqu-test").addEventListener("click", async () => {
    setStatus("测试后端连接中...");
    const btn = el("cqu-test");
    btn.disabled = true;
    try {
      const res = await chrome.runtime.sendMessage({ type: "testConnection" });
      setStatus(res && res.ok ? `✅ ${res.message}` : `❌ ${res && res.message ? res.message : "连接失败"}`, res && res.ok ? "ok" : "fail");
    } catch (err) {
      setStatus(`测试失败：${err.message}`, "fail");
    } finally {
      btn.disabled = false;
    }
  });

  el("cqu-submit").addEventListener("click", async () => {
    const channel = el("cqu-channel").value.trim();
    const shopName = el("cqu-shop").value.trim();
    const mobilePhone = el("cqu-mobile").value.trim();
    const dns = el("cqu-dns").value.trim();
    if (!channel) { setStatus("请填写渠道 channel", "fail"); return; }
    if (!dns) { setStatus("请填写 DNS", "fail"); return; }
    if (!state.cookies.length) { setStatus("当前没有可上报的 Cookie", "fail"); return; }

    const btn = el("cqu-submit");
    btn.disabled = true;
    setStatus("上报中...");
    try {
      const res = await chrome.runtime.sendMessage({
        type: "submitManual",
        channel,
        shopName,
        mobilePhone,
        dns,
        cookies: state.cookies,
        headers: state.headers || null,
      });
      if (!res || !res.ok) {
        setStatus(res && res.message ? res.message : "提交失败", "fail");
        return;
      }
      setStatus(`✅ 已${res.is_new ? "新增" : "更新"} ${res.stored} 条 Cookie`, "ok");
    } catch (err) {
      setStatus(`提交失败：${err.message}`, "fail");
    } finally {
      btn.disabled = false;
    }
  });

  el("cqu-refresh").addEventListener("click", async () => {
    setStatus("刷新页面中，稍候自动重新获取...");
    try {
      await chrome.runtime.sendMessage({ type: "reloadTab" });
    } catch (err) {
      setStatus(`刷新失败：${err.message}`, "fail");
    }
    // 页面刷新后由本 tab 重新注入的 content script 消费 checkRefreshPending 并自动展开抓取
  });

  // content script 上下文无 chrome.runtime.openOptionsPage，经 background 转发
  el("cqu-options").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "openOptionsPage" }).catch(() => { /* 忽略 */ });
  });

  // 应用捕获结果：captureHeaders 触发页面刷新后，一并重新抓取当前页面 cookie，
  // 保证「一个按钮同时拿 cookie + headers」；headers 捕获失败也抓 cookie，可只上报 cookie。
  function applyHeaders(payload) {
    if (payload.ok && payload.headers) {
      state.headers = payload.headers;
      el("cqu-hdr-count").textContent = `${Object.keys(payload.headers).length} 个请求头`;
      el("cqu-hdr-url").textContent = `来自：${payload.url || ""}`;
      panel.style.display = "block";
      setStatus("已捕获请求头", "ok");
    } else {
      state.headers = null;
      el("cqu-hdr-count").textContent = "捕获失败";
      setStatus(payload.error || "捕获失败", "fail");
    }
    refreshCookies();
  }

  // 接收 background 的 Headers 捕获结果（页面刷新后本实例为新注入的 content script）
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "headersCaptured") {
      applyHeaders(msg);
    }
  });

  // 兜底：捕获完成但本实例注入晚于 sendMessage 投递时，经 background 代读 storage.session 消费
  chrome.runtime.sendMessage({ type: "getCapturedHeaders" }).then((res) => {
    if (res && res.ok && res.found) {
      applyHeaders(res);
    }
  }).catch(() => { /* 忽略 */ });

  // 刷新后自动恢复：用户点过「刷新页面并重新获取」时，本 tab 重新注入后自动展开面板并抓取
  chrome.runtime.sendMessage({ type: "checkRefreshPending" }).then((res) => {
    if (res && res.ok && res.pending) {
      panel.style.display = "block";
      refreshCookies();
    }
  }).catch(() => { /* 后台不可达时不阻塞 */ });
})();
