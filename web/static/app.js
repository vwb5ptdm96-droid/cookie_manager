const state = {
    tasks: [],
    deleteTaskId: null,
    currentView: "tasks",
};

const viewTitles = {
    tasks: "任务管理",
    cookies: "Cookie 数据",
    runs: "运行记录",
    settings: "系统设置",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

document.addEventListener("DOMContentLoaded", async () => {
    bindEvents();
    await loadScripts();
    await loadTasks();
    setInterval(loadTasks, 5000);
});

function bindEvents() {
    $("#addTaskButton").addEventListener("click", () => openDrawer());
    $("#closeDrawerButton").addEventListener("click", closeDrawer);
    $("#cancelButton").addEventListener("click", closeDrawer);
    $("#drawerBackdrop").addEventListener("click", closeDrawer);
    $("#taskForm").addEventListener("submit", saveTask);
    $("#togglePassword").addEventListener("click", togglePassword);
    $("#refreshListButton").addEventListener("click", loadTasks);
    $("#refreshRunsButton").addEventListener("click", loadRuns);
    $("#refreshCookiesButton").addEventListener("click", loadCookies);
    $("#searchInput").addEventListener("input", renderTasks);
    bindStatusFilter();
    $("#cancelDeleteButton").addEventListener("click", closeDeleteDialog);
    $("#confirmDeleteButton").addEventListener("click", confirmDelete);
    $$(".nav-item").forEach((button) => button.addEventListener("click", switchView));
}

function bindStatusFilter() {
    const menu = $("#statusFilterMenu");
    const trigger = menu.querySelector(".select-trigger");
    const options = [...menu.querySelectorAll("[role='option']")];

    trigger.addEventListener("click", () => {
        const isOpen = menu.classList.toggle("open");
        trigger.setAttribute("aria-expanded", String(isOpen));
    });

    options.forEach((option) => {
        option.addEventListener("click", () => {
            $("#statusFilter").value = option.dataset.value;
            $("#statusFilterLabel").textContent = option.textContent;
            options.forEach((item) => {
                item.setAttribute("aria-selected", String(item === option));
            });
            closeStatusFilter();
            renderTasks();
        });
    });

    document.addEventListener("click", (event) => {
        if (!menu.contains(event.target)) closeStatusFilter();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeStatusFilter();
    });
}

function closeStatusFilter() {
    const menu = $("#statusFilterMenu");
    if (!menu) return;
    menu.classList.remove("open");
    menu.querySelector(".select-trigger").setAttribute("aria-expanded", "false");
}

async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `请求失败：${response.status}`);
    return data;
}

async function loadTasks() {
    try {
        const data = await api("/api/tasks");
        state.tasks = data.tasks;
        renderStats(data.stats || {});
        renderTasks();
        $("#lastSyncText").textContent = `同步于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
        if (state.currentView === "runs") loadRuns();
        if (state.currentView === "cookies") loadCookies();
    } catch (error) {
        showToast(error.message, true);
    }
}

function renderStats(stats) {
    $("#statTotal").textContent = stats.total || 0;
    $("#statNormal").textContent = stats.normal || 0;
    $("#statFailed").textContent = stats.failed || 0;
    $("#statDisabled").textContent = stats.disabled || 0;
}

function renderTasks() {
    const query = $("#searchInput").value.trim().toLowerCase();
    const filter = $("#statusFilter").value;
    const tasks = state.tasks.filter((task) => {
        const haystack = `${task.name} ${task.site} ${task.account} ${task.username || ""}`.toLowerCase();
        const matchesQuery = !query || haystack.includes(query);
        const visualStatus = task.enabled ? task.last_result : "disabled";
        const matchesStatus = filter === "all" || visualStatus === filter;
        return matchesQuery && matchesStatus;
    });

    const body = $("#taskTableBody");
    if (!tasks.length) {
        body.innerHTML = '<tr><td colspan="8" class="empty-state">没有符合条件的任务</td></tr>';
        return;
    }

    body.innerHTML = tasks.map((task) => {
        const status = getTaskStatus(task);
        const lastTime = task.checked_at || task.refreshed_at || task.updated_at;
        return `
            <tr>
                <td>
                    <div class="task-name">${escapeHtml(task.name)}</div>
                    <div class="task-subtext">
                        <input class="task-toggle" type="checkbox" ${task.enabled ? "checked" : ""}
                            onchange="toggleTask(${task.id}, this.checked)" aria-label="启用任务">
                        ${task.enabled ? "已启用" : "已停用"}
                    </div>
                </td>
                <td>${escapeHtml(task.site)}</td>
                <td>
                    <div>${escapeHtml(task.account)}</div>
                    <div class="cell-subtext">${escapeHtml(task.username || "未填写登录账号")}</div>
                </td>
                <td><div class="url-cell" title="${escapeHtml(task.probe_url)}">${escapeHtml(task.probe_url)}</div></td>
                <td>
                    <span class="badge ${status.className}">${status.label}</span>
                    ${task.last_error ? `<div class="cell-subtext error-text" title="${escapeHtml(task.last_error)}">${escapeHtml(task.last_error)}</div>` : ""}
                </td>
                <td>
                    <div>${formatTime(lastTime)}</div>
                    <div class="cell-subtext">${task.has_cookie ? `Cookie ${task.cookie_length || 0} 字符` : "尚无 Cookie"}</div>
                </td>
                <td>${escapeHtml(task.refresh_script.split(".").pop() + ".py")}</td>
                <td>
                    <div class="row-actions">
                        <button class="text-button" onclick="runAction(${task.id}, 'probe')">探测</button>
                        <button class="text-button" onclick="runAction(${task.id}, 'refresh')">刷新</button>
                        <button class="text-button" onclick="editTask(${task.id})">编辑</button>
                        <button class="text-button danger" onclick="openDeleteDialog(${task.id})">删除</button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function getTaskStatus(task) {
    if (!task.enabled) return { label: "已停用", className: "disabled" };
    if (task.last_result === "running") return { label: "执行中", className: "running" };
    if (task.last_result === "success") {
        return { label: task.last_status ? `正常 ${task.last_status}` : "执行成功", className: "success" };
    }
    if (task.last_result === "failed") {
        return { label: task.last_status ? `异常 ${task.last_status}` : "执行失败", className: "failed" };
    }
    return { label: "等待执行", className: "idle" };
}

async function loadRuns() {
    try {
        const { runs } = await api("/api/runs?limit=100");
        $("#runTableBody").innerHTML = runs.length ? runs.map((run) => `
            <tr>
                <td>${escapeHtml(run.task_name)}</td>
                <td>${run.action === "probe" ? "探测" : "刷新"}</td>
                <td><span class="badge ${run.status === "success" ? "success" : run.status === "failed" ? "failed" : "running"}">${runStatusLabel(run.status)}</span></td>
                <td>${run.http_status || "—"}</td>
                <td>${formatTime(run.started_at)}</td>
                <td>${formatTime(run.finished_at)}</td>
                <td class="${run.status === "failed" ? "error-text" : ""}" title="${escapeHtml(run.message || "")}">${escapeHtml(run.message || "—")}</td>
            </tr>
        `).join("") : '<tr><td colspan="7" class="empty-state">暂无运行记录</td></tr>';
    } catch (error) {
        showToast(error.message, true);
    }
}

function switchView(event) {
    const view = event.currentTarget.dataset.view;
    if (view === state.currentView) return;
    state.currentView = view;
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
    ["tasks", "runs", "cookies", "settings"].forEach((name) => {
        const panel = $(`#${name}View`);
        const isActive = name === view;
        panel.classList.toggle("hidden", !isActive);
        panel.classList.toggle("view-active", isActive);
    });
    $("h1").textContent = viewTitles[view] || "任务管理";
    if (view === "runs") loadRuns();
    if (view === "cookies") loadCookies();
}

async function loadCookies() {
    try {
        const { cookies } = await api("/api/cookies");
        $("#cookieTableBody").innerHTML = cookies.length ? cookies.map((cookie) => `
            <tr>
                <td>${escapeHtml(cookie.site)}</td>
                <td>${escapeHtml(cookie.account)}</td>
                <td>${cookie.cookie_length || 0} 字符</td>
                <td>${cookie.last_status || "—"}</td>
                <td>${formatTime(cookie.checked_at)}</td>
                <td>${formatTime(cookie.refreshed_at)}</td>
                <td>${formatTime(cookie.updated_at)}</td>
            </tr>
        `).join("") : '<tr><td colspan="7" class="empty-state">暂无 Cookie 数据</td></tr>';
    } catch (error) {
        showToast(error.message, true);
    }
}

function openDrawer(task = null) {
    $("#taskForm").reset();
    $("#taskId").value = task?.id || "";
    $("#drawerTitle").textContent = task ? "编辑任务" : "新增任务";
    $("#enabled").checked = task ? task.enabled : true;
    $("#okStatuses").value = task?.ok_statuses_text || "200";
    $("#timeoutSeconds").value = task?.timeout_seconds || 15;
    $("#profileDir").value = task?.profile_dir || "Default";
    $("#cdpPort").value = task?.cdp_port || 9222;
    if (task) fillForm(task);
    $("#drawerBackdrop").classList.remove("hidden");
    $("#taskDrawer").classList.add("open");
    $("#taskDrawer").setAttribute("aria-hidden", "false");
    setTimeout(() => $("#name").focus(), 150);
}

function closeDrawer() {
    $("#drawerBackdrop").classList.add("hidden");
    $("#taskDrawer").classList.remove("open");
    $("#taskDrawer").setAttribute("aria-hidden", "true");
}

function fillForm(task) {
    $("#name").value = task.name || "";
    $("#site").value = task.site || "";
    $("#account").value = task.account || "";
    $("#username").value = task.username || "";
    $("#password").value = task.password || "";
    $("#probeUrl").value = task.probe_url || "";
    $("#refreshScript").value = task.refresh_script || "";
    $("#loginUrl").value = task.login_url || "";
    $("#browserPath").value = task.browser_path || "";
    $("#userDataDir").value = task.user_data_dir || "";
    $("#headers").value = task.headers && Object.keys(task.headers).length
        ? JSON.stringify(task.headers, null, 2) : "";
}

async function editTask(taskId) {
    try {
        const { task } = await api(`/api/tasks/${taskId}`);
        openDrawer(task);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function saveTask(event) {
    event.preventDefault();
    const button = $("#saveButton");
    button.disabled = true;
    try {
        const taskId = $("#taskId").value;
        const payload = collectForm();
        await api(taskId ? `/api/tasks/${taskId}` : "/api/tasks", {
            method: taskId ? "PUT" : "POST",
            body: JSON.stringify(payload),
        });
        showToast(taskId ? "任务已保存" : "任务已创建");
        closeDrawer();
        await loadTasks();
    } catch (error) {
        showToast(error.message, true);
    } finally {
        button.disabled = false;
    }
}

function collectForm() {
    return {
        name: $("#name").value,
        site: $("#site").value,
        account: $("#account").value,
        username: $("#username").value,
        password: $("#password").value,
        probe_url: $("#probeUrl").value,
        method: "GET",
        ok_statuses_text: $("#okStatuses").value,
        timeout_seconds: Number($("#timeoutSeconds").value),
        refresh_script: $("#refreshScript").value,
        enabled: $("#enabled").checked,
        login_url: $("#loginUrl").value,
        browser_path: $("#browserPath").value,
        user_data_dir: $("#userDataDir").value,
        profile_dir: $("#profileDir").value,
        cdp_port: Number($("#cdpPort").value),
        headers: $("#headers").value,
    };
}

async function toggleTask(taskId, enabled) {
    try {
        await api(`/api/tasks/${taskId}/enabled`, {
            method: "PATCH",
            body: JSON.stringify({ enabled }),
        });
        showToast(enabled ? "定时探测已启用" : "定时探测已停用");
        await loadTasks();
    } catch (error) {
        showToast(error.message, true);
        await loadTasks();
    }
}

async function runAction(taskId, action) {
    try {
        await api(`/api/tasks/${taskId}/${action}`, { method: "POST", body: "{}" });
        showToast(action === "probe" ? "探测任务已提交" : "刷新脚本已提交");
        await loadTasks();
    } catch (error) {
        showToast(error.message, true);
    }
}

function openDeleteDialog(taskId) {
    state.deleteTaskId = taskId;
    $("#confirmBackdrop").classList.remove("hidden");
}

function closeDeleteDialog() {
    state.deleteTaskId = null;
    $("#confirmBackdrop").classList.add("hidden");
}

async function confirmDelete() {
    if (!state.deleteTaskId) return;
    try {
        await api(`/api/tasks/${state.deleteTaskId}`, { method: "DELETE" });
        showToast("任务已删除");
        closeDeleteDialog();
        await loadTasks();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function loadScripts() {
    try {
        const { scripts } = await api("/api/scripts");
        $("#scriptOptions").innerHTML = scripts.map((script) => `<option value="${escapeHtml(script)}"></option>`).join("");
    } catch (error) {
        showToast(error.message, true);
    }
}

function togglePassword() {
    const input = $("#password");
    const visible = input.type === "text";
    input.type = visible ? "password" : "text";
    $("#togglePassword").textContent = visible ? "显示" : "隐藏";
}

function runStatusLabel(status) {
    return { queued: "排队中", running: "执行中", success: "成功", failed: "失败" }[status] || status;
}

function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { hour12: false });
}

function showToast(message, isError = false) {
    const toast = document.createElement("div");
    toast.className = `toast${isError ? " error" : ""}`;
    toast.textContent = message;
    $("#toastContainer").appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    }[char]));
}

window.editTask = editTask;
window.toggleTask = toggleTask;
window.runAction = runAction;
window.openDeleteDialog = openDeleteDialog;
