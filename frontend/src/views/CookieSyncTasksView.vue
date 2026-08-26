<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { EditPen } from "@element-plus/icons-vue";
import { ArrowDown } from "@element-plus/icons-vue";

import {
  cloneCookieSyncTask,
  createCookieSyncTask,
  deleteCookieSyncTask,
  executeCookieSyncTaskCheck,
  executeCookieSyncTaskRepair,
  fetchCookieSyncTasks,
  toggleCookieSyncTask,
  updateCookieSyncTask,
  type CookieSyncTaskCreatePayload,
  type CookieSyncTaskItem,
  type CookieSyncTaskUpdatePayload,
} from "@/api/cookieSyncTasks";
import {
  createCookieSyncMapping,
  deleteCookieSyncMapping,
  fetchCookieSyncMappings,
  updateCookieSyncMapping,
  type CookieSyncMappingCreatePayload,
  type CookieSyncMappingItem,
} from "@/api/cookieSyncMappings";

// ── 采集任务 ──
const tasks = ref<CookieSyncTaskItem[]>([]);
const taskLoading = ref(false);
const submitting = ref(false);
const checkingCode = ref<string | null>(null);
const repairingCode = ref<string | null>(null);
const togglingCode = ref<string | null>(null);
const taskDialogVisible = ref(false);
const editingTask = ref<CookieSyncTaskItem | null>(null);
const activeTab = ref("detect");
const filters = reactive({ status: "", keyword: "" });

const form = reactive<CookieSyncTaskCreatePayload>({
  cookie_sync_task_name: "",
  cookie_table: "ods_cookie_playwright",
  channel: "",
  shop_name: null,
  mobile_phone: null,
  dns: null,
  check_url: "",
  http_method: "GET",
  http_headers: null,
  http_body: null,
  success_rule: null,
  failure_rule: null,
  cron_expression: null,
  check_timeout_seconds: 30,
  retry_count: 0,
  sync_wait_timeout_seconds: 180,
});

// ── 映射管理 ──
const mappings = ref<CookieSyncMappingItem[]>([]);
const mappingLoading = ref(false);
const mappingDialogVisible = ref(false);
const editingMapping = ref<CookieSyncMappingItem | null>(null);
const mappingSubmitting = ref(false);
const mappingForm = reactive<CookieSyncMappingCreatePayload>({
  worker_id: "",
  domain: "",
  channel: "",
  shop_name: null,
  mobile_phone: null,
  dns: "",
  remark: null,
});

const tabName = ref("tasks");

// ── 扩展接入展示 ──

function apiBaseUrl(): string {
  // 后端端口由 .env 的 APP_PORT 决定；生产环境前端与后端同源，直接用当前 origin 动态取，不写死端口
  return `${window.location.origin}/api`;
}

const apiKeyHint = "配置在服务端 .env，为安全不在此展示；留空则关闭鉴权（仅限本地联调）";

// ── JSON 编辑器（检测请求头/请求体） ──
const jsonEditorVisible = ref(false);
const jsonEditorTarget = ref<"http_headers" | "http_body" | null>(null);
const jsonEditorTemp = ref("");

function openJsonEditor(field: "http_headers" | "http_body"): void {
  jsonEditorTarget.value = field;
  jsonEditorTemp.value = form[field] ?? "";
  jsonEditorVisible.value = true;
}

function saveJsonEditor(): void {
  const field = jsonEditorTarget.value;
  if (!field) return;
  const raw = jsonEditorTemp.value.trim();
  if (!raw) {
    form[field] = null;
    jsonEditorVisible.value = false;
    return;
  }
  const converted = formatLooseJson(raw);
  if (converted.error) {
    ElMessage.error(converted.error);
    return;
  }
  form[field] = converted.json;
  jsonEditorVisible.value = false;
}

function validateJsonEditor(): void {
  const result = formatLooseJson(jsonEditorTemp.value);
  if (result.error) {
    ElMessage.error(result.error);
  } else {
    jsonEditorTemp.value = result.json;
    ElMessage.success("格式有效，已自动转换");
  }
}

function formatLooseJson(input: string): { json: string; error?: string } {
  try { JSON.parse(input); return { json: input }; } catch { /* 继续 */ }
  let s = input.trim();
  try {
    s = s.replace(/:\s*'((?:[^'\\]|\\.)*)'/g, (_m, content: string) => {
      return ': "' + content.replace(/"/g, '\\"') + '"';
    });
    s = s.replace(/'([^']+)'\s*:/g, '"$1":');
    s = s.replace(/,\s*([}\]])/g, '$1');
    JSON.parse(s);
    return { json: s };
  } catch {
    return { json: input, error: "无法解析，请粘贴标准 JSON 或 Python 字典格式" };
  }
}

// ── 判定规则编辑器 ──
type RuleType = "status_code" | "contains" | "equals" | "";

interface RuleConfig {
  type: RuleType;
  statusCode: number;
  containsPattern: string;
  equalsValue: string;
}

const ruleDefaults: RuleConfig = {
  type: "",
  statusCode: 200,
  containsPattern: "",
  equalsValue: "",
};

function ruleToJson(rule: RuleConfig): string | null {
  if (!rule.type) return null;
  if (rule.type === "status_code") return JSON.stringify({ status_code: rule.statusCode });
  if (rule.type === "contains") {
    if (!rule.containsPattern) return null;
    return JSON.stringify({ contains: rule.containsPattern });
  }
  if (rule.type === "equals") {
    if (!rule.equalsValue) return null;
    return JSON.stringify({ equals: rule.equalsValue });
  }
  return null;
}

function ruleFromJson(json: string | null | undefined): RuleConfig {
  const def = { ...ruleDefaults };
  if (!json) return def;
  try {
    const obj = JSON.parse(json);
    if (typeof obj === "object" && obj !== null) {
      if ("status_code" in obj) return { ...def, type: "status_code", statusCode: obj.status_code };
      if ("contains" in obj) {
        const val = obj.contains;
        return { ...def, type: "contains", containsPattern: typeof val === "string" ? val : val?.value ?? "" };
      }
      if ("equals" in obj) {
        const val = obj.equals;
        return { ...def, type: "equals", equalsValue: typeof val === "string" ? val : val?.value ?? "" };
      }
    }
  } catch { /* 忽略 */ }
  return def;
}

const successRule = reactive<RuleConfig>({ ...ruleDefaults });
const failureRule = reactive<RuleConfig>({ ...ruleDefaults });

function syncRulesFromForm(): void {
  Object.assign(successRule, ruleFromJson(form.success_rule));
  Object.assign(failureRule, ruleFromJson(form.failure_rule));
}

function syncRulesToForm(): void {
  form.success_rule = ruleToJson(successRule);
  form.failure_rule = ruleToJson(failureRule);
}

const filteredTasks = computed(() =>
  tasks.value.filter((item) => {
    const s = !filters.status || item.status === filters.status;
    const kw = filters.keyword.trim().toLowerCase();
    const m =
      !kw ||
      [item.cookie_sync_task_name, item.cookie_sync_task_code, item.channel, item.shop_name, item.dns, item.check_url]
        .join(" ")
        .toLowerCase()
        .includes(kw);
    return s && m;
  }),
);

const STATUS_LABELS: Record<string, string> = {
  PASS: "通过",
  FAIL: "失败",
  PENDING: "待检测",
  DISABLED: "已停用",
  SYNCING: "采集同步中",
};

function statusType(status: string): "success" | "danger" | "warning" | "info" {
  if (status === "PASS") return "success";
  if (status === "FAIL") return "danger";
  if (status === "SYNCING") return "warning";
  if (status === "PENDING") return "info";
  return "info";
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

function formatBeijingTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

// ── 采集任务加载与操作 ──

async function loadTasks(): Promise<void> {
  taskLoading.value = true;
  try {
    const data = await fetchCookieSyncTasks();
    tasks.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载采集任务失败");
  } finally {
    taskLoading.value = false;
  }
}

function openTaskCreate(): void {
  editingTask.value = null;
  Object.assign(form, {
    cookie_sync_task_name: "",
    cookie_table: "ods_cookie_playwright",
    channel: "",
    shop_name: null,
    mobile_phone: null,
    dns: null,
    check_url: "",
    http_method: "GET",
    http_headers: null,
    http_body: null,
    success_rule: null,
    failure_rule: null,
    cron_expression: null,
    check_timeout_seconds: 30,
    retry_count: 0,
    sync_wait_timeout_seconds: 180,
  });
  Object.assign(successRule, { ...ruleDefaults });
  Object.assign(failureRule, { ...ruleDefaults });
  activeTab.value = "detect";
  taskDialogVisible.value = true;
}

function openTaskEdit(task: CookieSyncTaskItem): void {
  editingTask.value = task;
  Object.assign(form, {
    cookie_sync_task_name: task.cookie_sync_task_name,
    cookie_table: task.cookie_table,
    channel: task.channel,
    shop_name: task.shop_name,
    mobile_phone: task.mobile_phone,
    dns: task.dns,
    check_url: task.check_url,
    http_method: task.http_method,
    http_headers: task.http_headers,
    http_body: task.http_body,
    success_rule: task.success_rule,
    failure_rule: task.failure_rule,
    cron_expression: task.cron_expression,
    check_timeout_seconds: task.check_timeout_seconds,
    retry_count: task.retry_count,
    sync_wait_timeout_seconds: task.sync_wait_timeout_seconds,
  });
  syncRulesFromForm();
  activeTab.value = "detect";
  taskDialogVisible.value = true;
}

async function handleTaskSubmit(): Promise<void> {
  syncRulesToForm();
  submitting.value = true;
  try {
    if (editingTask.value) {
      await updateCookieSyncTask(editingTask.value.cookie_sync_task_code, form as CookieSyncTaskUpdatePayload);
      ElMessage.success("采集任务已更新");
    } else {
      await createCookieSyncTask(form as CookieSyncTaskCreatePayload);
      ElMessage.success("采集任务已创建");
    }
    taskDialogVisible.value = false;
    editingTask.value = null;
    await loadTasks();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提交失败");
  } finally {
    submitting.value = false;
  }
}

async function handleCheck(task: CookieSyncTaskItem): Promise<void> {
  checkingCode.value = task.cookie_sync_task_code;
  try {
    const result = await executeCookieSyncTaskCheck(task.cookie_sync_task_code);
    const detail = (result as unknown as Record<string, string>).check_detail || "";
    await loadTasks();
    if (detail) {
      await ElMessageBox.alert(detail, `检测结果: ${statusLabel(result.status)}`, {
        confirmButtonText: "确定",
        dangerouslyUseHTMLString: false,
        message: detail,
        customClass: "check-result-dialog",
      });
    } else {
      ElMessage.success(`检测完成，结果：${statusLabel(result.status)}`);
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行检测失败");
  } finally {
    checkingCode.value = null;
  }
}

async function handleRepair(task: CookieSyncTaskItem): Promise<void> {
  repairingCode.value = task.cookie_sync_task_code;
  try {
    const result = await executeCookieSyncTaskRepair(task.cookie_sync_task_code);
    const detail = (result as unknown as Record<string, string>).check_detail || "";
    await loadTasks();
    if (detail) {
      await ElMessageBox.alert(detail, `执行修复结果: ${statusLabel(result.status)}`, {
        confirmButtonText: "确定",
        dangerouslyUseHTMLString: false,
        message: detail,
        customClass: "check-result-dialog",
      });
    } else {
      ElMessage.success(`已触发扩展采集，状态：${statusLabel(result.status)}`);
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行修复失败");
  } finally {
    repairingCode.value = null;
  }
}

async function handleClone(task: CookieSyncTaskItem): Promise<void> {
  try {
    await cloneCookieSyncTask(task.cookie_sync_task_code);
    ElMessage.success("任务已复制");
    await loadTasks();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "复制失败");
  }
}

async function handleDelete(task: CookieSyncTaskItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除采集任务「${task.cookie_sync_task_name}」吗？`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await deleteCookieSyncTask(task.cookie_sync_task_code);
    ElMessage.success("任务已删除");
    await loadTasks();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败");
  }
}

async function handleToggle(task: CookieSyncTaskItem): Promise<void> {
  togglingCode.value = task.cookie_sync_task_code;
  try {
    await toggleCookieSyncTask(task.cookie_sync_task_code, !task.enabled);
    ElMessage.success(task.enabled ? "任务已停用" : "任务已启用");
    await loadTasks();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "切换状态失败");
  } finally {
    togglingCode.value = null;
  }
}

function handleTaskAction(cmd: string, task: CookieSyncTaskItem): void {
  if (cmd === "repair") void handleRepair(task);
  else if (cmd === "clone") void handleClone(task);
  else if (cmd === "delete") void handleDelete(task);
  else if (cmd === "toggle") void handleToggle(task);
}

// ── 映射加载与操作 ──

async function loadMappings(): Promise<void> {
  mappingLoading.value = true;
  try {
    const data = await fetchCookieSyncMappings();
    mappings.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载映射失败");
  } finally {
    mappingLoading.value = false;
  }
}

function openMappingCreate(): void {
  editingMapping.value = null;
  Object.assign(mappingForm, {
    worker_id: "",
    domain: "",
    channel: "",
    shop_name: null,
    mobile_phone: null,
    dns: "",
    remark: null,
  });
  mappingDialogVisible.value = true;
}

function openMappingEdit(mapping: CookieSyncMappingItem): void {
  editingMapping.value = mapping;
  Object.assign(mappingForm, {
    worker_id: mapping.worker_id,
    domain: mapping.domain,
    channel: mapping.channel,
    shop_name: mapping.shop_name,
    mobile_phone: mapping.mobile_phone,
    dns: mapping.dns,
    remark: mapping.remark,
  });
  mappingDialogVisible.value = true;
}

async function handleMappingSubmit(): Promise<void> {
  // Spec REQ-008：dns 应与 domain 一致
  const norm = (s: string | null | undefined) => (s ?? "").trim().toLowerCase().replace(/^\./, "");
  if (mappingForm.domain && mappingForm.dns && norm(mappingForm.domain) !== norm(mappingForm.dns)) {
    ElMessage.error("dns 应与 domain 一致");
    return;
  }
  mappingSubmitting.value = true;
  try {
    if (editingMapping.value) {
      await updateCookieSyncMapping(editingMapping.value.id, mappingForm);
      ElMessage.success("映射已更新");
    } else {
      await createCookieSyncMapping(mappingForm as CookieSyncMappingCreatePayload);
      ElMessage.success("映射已创建");
    }
    mappingDialogVisible.value = false;
    editingMapping.value = null;
    await loadMappings();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提交失败");
  } finally {
    mappingSubmitting.value = false;
  }
}

async function handleMappingDelete(mapping: CookieSyncMappingItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除映射「${mapping.worker_id} / ${mapping.domain}」吗？`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await deleteCookieSyncMapping(mapping.id);
    ElMessage.success("映射已删除");
    await loadMappings();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败");
  }
}

function onTabChange(name: string): void {
  if (name === "tasks") void loadTasks();
  else if (name === "mappings") void loadMappings();
}

onMounted(() => {
  void loadTasks();
  void loadMappings();
});
</script>

<template>
  <section class="page-grid">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Cookie 扩展采集</h2>
          <p>采集任务定时/手动检测旧 cookie 有效性，失效时通过同事浏览器扩展补采新 cookie 并写回旧表，实现检测→补采→复检闭环。</p>
        </div>
      </div>

      <el-tabs v-model="tabName" @tab-change="onTabChange">
        <!-- ═══ 采集任务 ═══ -->
        <el-tab-pane label="采集任务" name="tasks">
          <div class="tab-toolbar">
            <el-select v-model="filters.status" clearable placeholder="状态" style="width: 180px">
              <el-option label="PENDING" value="PENDING" />
              <el-option label="PASS" value="PASS" />
              <el-option label="FAIL" value="FAIL" />
              <el-option label="SYNCING" value="SYNCING" />
              <el-option label="DISABLED" value="DISABLED" />
            </el-select>
            <el-input v-model="filters.keyword" clearable placeholder="搜索任务名称、渠道、店铺、DNS 或 API" />
            <el-button type="primary" @click="openTaskCreate">新增采集任务</el-button>
          </div>

          <div class="table-shell">
            <el-table v-loading="taskLoading" :data="filteredTasks" row-key="cookie_sync_task_code" empty-text="暂无采集任务。点击「新增采集任务」创建一条任务。">
              <el-table-column prop="cookie_sync_task_name" label="采集任务名称" min-width="180" />
              <el-table-column prop="cron_expression" label="调度" min-width="110">
                <template #default="{ row }">
                  <code>{{ row.cron_expression || "手动" }}</code>
                </template>
              </el-table-column>
              <el-table-column prop="channel" label="渠道" min-width="90" />
              <el-table-column prop="dns" label="DNS" min-width="150" show-overflow-tooltip />
              <el-table-column label="状态" min-width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusType(row.status)" effect="plain" size="small">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="最近检测" min-width="150">
                <template #default="{ row }">
                  <span class="cell-muted">{{ formatBeijingTime(row.last_checked_at) || "尚未执行" }}</span>
                </template>
              </el-table-column>
              <el-table-column label="最近同步" min-width="150">
                <template #default="{ row }">
                  <span class="cell-muted">{{ formatBeijingTime(row.last_sync_at) || "-" }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="300" fixed="right">
                <template #default="{ row }">
                  <div class="actions">
                    <el-button size="small" @click="openTaskEdit(row)">编辑</el-button>
                    <el-button
                      size="small" type="warning" plain
                      :disabled="!row.enabled || row.status === 'SYNCING'"
                      :loading="repairingCode === row.cookie_sync_task_code"
                      @click="handleRepair(row)"
                    >修复</el-button>
                    <el-button
                      size="small" type="primary"
                      :disabled="!row.enabled"
                      :loading="checkingCode === row.cookie_sync_task_code"
                      @click="handleCheck(row)"
                    >检测</el-button>
                    <el-dropdown trigger="click" @command="(cmd: string) => handleTaskAction(cmd, row)">
                      <el-button size="small">
                        更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                      </el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="clone">复制</el-dropdown-item>
                          <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                          <el-dropdown-item command="toggle" divided>{{ row.enabled ? "停用" : "启用" }}</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- ═══ 映射管理 ═══ -->
        <el-tab-pane label="映射管理" name="mappings">
          <div class="tab-toolbar">
            <p class="tab-tip">映射定义「采集者 → 业务记录」：扩展上报按 (worker_id, domain) 正向匹配写回旧表；采集任务失效时按业务键反向查 (worker_id, domain) 下发采集。</p>
            <el-button type="primary" @click="openMappingCreate">新增映射</el-button>
          </div>

          <div class="table-shell">
            <el-table v-loading="mappingLoading" :data="mappings" row-key="id" empty-text="暂无映射。添加映射后，扩展上报的 cookie 才能写回旧表。">
              <el-table-column prop="worker_id" label="采集者 worker_id" min-width="120" />
              <el-table-column prop="domain" label="域名" min-width="180" show-overflow-tooltip />
              <el-table-column prop="channel" label="渠道" min-width="90" />
              <el-table-column prop="shop_name" label="店铺" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">{{ row.shop_name || "-" }}</template>
              </el-table-column>
              <el-table-column prop="mobile_phone" label="手机号" min-width="120">
                <template #default="{ row }">{{ row.mobile_phone || "-" }}</template>
              </el-table-column>
              <el-table-column prop="dns" label="DNS" min-width="150" show-overflow-tooltip />
              <el-table-column label="最近上报" min-width="150">
                <template #default="{ row }">
                  <span class="cell-muted">{{ formatBeijingTime(row.last_report_at) || "-" }}</span>
                </template>
              </el-table-column>
              <el-table-column label="上报条数" min-width="90" align="center">
                <template #default="{ row }">{{ row.last_report_count }}</template>
              </el-table-column>
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <div class="actions">
                    <el-button size="small" @click="openMappingEdit(row)">编辑</el-button>
                    <el-button size="small" type="danger" plain @click="handleMappingDelete(row)">删除</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- ═══ 扩展接入 ═══ -->
        <el-tab-pane label="扩展接入" name="access">
          <div class="access-grid">
            <div class="access-card">
              <h3>后端连接信息</h3>
              <div class="kv-row">
                <span class="kv-key">API 地址</span>
                <code>{{ apiBaseUrl() }}</code>
              </div>
              <div class="kv-row">
                <span class="kv-key">接口密钥 COOKIE_SYNC_API_KEY</span>
                <code>{{ apiKeyHint }}</code>
              </div>
              <p class="access-note">
                密钥配置在后端 <code>.env</code> 的 <code>COOKIE_SYNC_API_KEY</code>。留空时关闭鉴权（仅限本地联调），生产环境必须配置，扩展请求头需携带 <code>X-API-Key</code>。
              </p>
            </div>

            <div class="access-card">
              <h3>Chrome 扩展安装</h3>
              <ol class="install-steps">
                <li>将 <code>extension/</code> 目录（仓库根下）拷贝到同事电脑，或从打包的 <code>.zip</code> 解压。</li>
                <li>打开 Chrome 扩展管理页 <code>chrome://extensions</code>，开启「开发者模式」。</li>
                <li>点击「加载已解压的扩展程序」，选择 <code>extension/</code> 目录。</li>
                <li>打开扩展的「选项页」/「配置页」，填写平台后端地址与密钥。</li>
                <li>扩展按周期轮询 <code>GET /api/tasks?worker_id=</code> 领取定向采集任务，读取浏览器 cookie 后上报。</li>
              </ol>
            </div>

            <div class="access-card">
              <h3>扩展契约接口</h3>
              <div class="endpoint-list">
                <div class="endpoint">
                  <code class="method">GET</code><code>/api/ping</code><span>测试连接（无鉴权）</span>
                </div>
                <div class="endpoint">
                  <code class="method">POST</code><code>/api/request</code><span>采集脚本请求同步 {domains, worker_ids}</span>
                </div>
                <div class="endpoint">
                  <code class="method">GET</code><code>/api/tasks</code><span>轮询待处理任务 {task_id, worker, domains}</span>
                </div>
                <div class="endpoint">
                  <code class="method">POST</code><code>/api/tasks/{id}/report</code><span>上报读取到的 cookie</span>
                </div>
                <div class="endpoint">
                  <code class="method">POST</code><code>/api/cookies</code><span>定时兜底/立即同步直推</span>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>

    <!-- 采集任务 创建/编辑弹窗 -->
    <el-dialog
      v-model="taskDialogVisible"
      :title="editingTask ? '编辑采集任务' : '新增采集任务'"
      width="780px"
      @close="editingTask = null"
    >
      <el-tabs v-model="activeTab">
        <el-tab-pane label="检测配置" name="detect">
          <el-form label-width="140px" class="task-form">
            <div class="form-section">
              <div class="form-section-title">请求配置</div>
              <el-form-item label="采集任务名称" required>
                <el-input v-model="form.cookie_sync_task_name" placeholder="例如：店铺A cookie 检测" />
              </el-form-item>
              <el-form-item label="请求 URL" required>
                <el-input v-model="form.check_url" placeholder="https://..." />
              </el-form-item>
              <el-row :gutter="12">
                <el-col :span="6">
                  <el-form-item label="请求方法">
                    <el-select v-model="form.http_method">
                      <el-option label="GET" value="GET" />
                      <el-option label="POST" value="POST" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="9">
                  <el-form-item label="请求头">
                    <el-input v-model="form.http_headers" placeholder="点击展开编辑" readonly @click="openJsonEditor('http_headers')">
                      <template #suffix>
                        <el-icon style="cursor:pointer; color: var(--color-primary);" @click.stop="openJsonEditor('http_headers')">
                          <EditPen />
                        </el-icon>
                      </template>
                    </el-input>
                  </el-form-item>
                </el-col>
                <el-col :span="9">
                  <el-form-item label="请求体">
                    <el-input v-model="form.http_body" placeholder="点击展开编辑" readonly @click="openJsonEditor('http_body')">
                      <template #suffix>
                        <el-icon style="cursor:pointer; color: var(--color-primary);" @click.stop="openJsonEditor('http_body')">
                          <EditPen />
                        </el-icon>
                      </template>
                    </el-input>
                  </el-form-item>
                </el-col>
              </el-row>
            </div>

            <div class="form-section">
              <div class="form-section-title">Cookie 数据源</div>
              <el-form-item label="cookie 表">
                <el-input v-model="form.cookie_table" placeholder="ods_cookie_playwright" />
              </el-form-item>
              <el-row :gutter="12">
                <el-col :span="8">
                  <el-form-item label="渠道" required>
                    <el-input v-model="form.channel" placeholder="例如 KUAISHOU" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="店铺名称">
                    <el-input v-model="form.shop_name" placeholder="可选" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="手机号">
                    <el-input v-model="form.mobile_phone" placeholder="可选" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="DNS">
                <el-input v-model="form.dns" placeholder="可选" />
              </el-form-item>
            </div>

            <div class="form-section">
              <div class="form-section-title">判定规则</div>
              <p class="form-section-desc">基于 HTTP 响应状态码和响应体判断。不配置规则则默认状态码 2xx/3xx 为通过。失效时触发扩展采集。</p>
              <el-row :gutter="24">
                <el-col :span="12">
                  <div class="rule-card rule-card-success">
                    <div class="rule-card-header">✅ 通过条件</div>
                    <el-form label-width="70px" class="rule-form">
                      <el-form-item label="条件类型">
                        <el-select v-model="successRule.type" clearable placeholder="请选择" @change="syncRulesToForm">
                          <el-option label="状态码等于" value="status_code" />
                          <el-option label="正则匹配" value="contains" />
                          <el-option label="JSON路径等于" value="equals" />
                        </el-select>
                      </el-form-item>
                      <template v-if="successRule.type === 'status_code'">
                        <el-form-item label="状态码">
                          <el-input-number v-model="successRule.statusCode" :min="100" :max="599" @change="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <template v-if="successRule.type === 'contains'">
                        <el-form-item label="正则匹配">
                          <el-input v-model="successRule.containsPattern" placeholder="登录失效|session.*expired" @input="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <template v-if="successRule.type === 'equals'">
                        <el-form-item label="等于值">
                          <el-input v-model="successRule.equalsValue" placeholder="ok" @input="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <div v-if="!successRule.type" class="rule-tip">未配置 — 默认通过</div>
                    </el-form>
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="rule-card rule-card-failure">
                    <div class="rule-card-header">❌ 失败条件</div>
                    <el-form label-width="70px" class="rule-form">
                      <el-form-item label="条件类型">
                        <el-select v-model="failureRule.type" clearable placeholder="请选择" @change="syncRulesToForm">
                          <el-option label="状态码等于" value="status_code" />
                          <el-option label="正则匹配" value="contains" />
                          <el-option label="JSON路径等于" value="equals" />
                        </el-select>
                      </el-form-item>
                      <template v-if="failureRule.type === 'status_code'">
                        <el-form-item label="状态码">
                          <el-input-number v-model="failureRule.statusCode" :min="100" :max="599" @change="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <template v-if="failureRule.type === 'contains'">
                        <el-form-item label="正则匹配">
                          <el-input v-model="failureRule.containsPattern" placeholder="登录失效|error|失败" @input="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <template v-if="failureRule.type === 'equals'">
                        <el-form-item label="等于值">
                          <el-input v-model="failureRule.equalsValue" placeholder="10008" @input="syncRulesToForm" />
                        </el-form-item>
                      </template>
                      <div v-if="!failureRule.type" class="rule-tip">未配置 — 仅参考通过条件</div>
                    </el-form>
                  </div>
                </el-col>
              </el-row>
            </div>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="高级调度" name="schedule">
          <el-form label-width="160px" class="task-form">
            <el-form-item label="cron 表达式">
              <el-input v-model="form.cron_expression" placeholder="留空为仅手动触发，例如 */30 * * * *" />
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="检测超时(秒)">
                  <el-input-number v-model="form.check_timeout_seconds" :min="5" :max="300" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="失败重试次数">
                  <el-input-number v-model="form.retry_count" :min="0" :max="10" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="同步设置" name="sync">
          <el-form label-width="200px" class="task-form">
            <el-form-item label="等待上报超时(秒)">
              <el-input-number v-model="form.sync_wait_timeout_seconds" :min="10" :max="3600" />
            </el-form-item>
            <p class="form-section-desc">
              检测失效后下发扩展采集任务，在等待超时内同事扩展上报新 cookie 并写回旧表则复检；超过该秒数未上报则任务标记 FAIL 并飞书通知。
            </p>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <!-- JSON 编辑器对话框 -->
      <el-dialog
        v-model="jsonEditorVisible"
        :title="jsonEditorTarget === 'http_headers' ? '编辑请求头' : '编辑请求体'"
        width="700px"
        :close-on-click-modal="false"
        append-to-body
        @close="jsonEditorTarget = null"
      >
        <p class="json-editor-desc">支持标准 JSON、Python 字典、JavaScript 对象格式。点击"格式化"自动转换。</p>
        <el-input
          v-model="jsonEditorTemp"
          type="textarea"
          :rows="14"
          placeholder="{
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0...',
}"
          style="font-family: var(--el-font-family-mono, monospace); font-size: 13px;"
        />
        <template #footer>
          <div class="dialog-actions">
            <el-button @click="jsonEditorVisible = false">取消</el-button>
            <el-button @click="validateJsonEditor">验证格式</el-button>
            <el-button type="primary" @click="saveJsonEditor">保存</el-button>
          </div>
        </template>
      </el-dialog>

      <template #footer>
        <div class="dialog-actions">
          <el-button @click="taskDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleTaskSubmit">
            {{ editingTask ? "保存修改" : "创建任务" }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 映射 创建/编辑弹窗 -->
    <el-dialog
      v-model="mappingDialogVisible"
      :title="editingMapping ? '编辑映射' : '新增映射'"
      width="620px"
      @close="editingMapping = null"
    >
      <el-form label-width="110px" class="task-form">
        <el-form-item label="采集者 worker_id" required>
          <el-input v-model="mappingForm.worker_id" placeholder="同事标识，例如 同事A" />
        </el-form-item>
        <el-form-item label="域名" required>
          <el-input v-model="mappingForm.domain" placeholder="store.weixin.qq.com" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="渠道" required>
              <el-input v-model="mappingForm.channel" placeholder="WEIXIN" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="DNS" required>
              <el-input v-model="mappingForm.dns" placeholder="store.weixin.qq.com" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="店铺名称">
              <el-input v-model="mappingForm.shop_name" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号">
              <el-input v-model="mappingForm.mobile_phone" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="mappingForm.remark" placeholder="可选" />
        </el-form-item>
        <p class="form-section-desc">(worker_id, domain) 为唯一键。删除映射前会检查是否有启用的采集任务依赖该业务记录。</p>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="mappingDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="mappingSubmitting" @click="handleMappingSubmit">
            {{ editingMapping ? "保存修改" : "创建映射" }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.page-grid {
  display: grid;
  gap: 16px;
}

.panel {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.panel-header h2,
.panel-header p {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0 16px;
}

.tab-toolbar .tab-tip {
  flex: 1;
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cell-muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.form-section {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-subtle);
}

.form-section-title {
  margin-bottom: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.form-section-desc {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.rule-card {
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.rule-card-success {
  border-top: 3px solid var(--color-success);
}

.rule-card-failure {
  border-top: 3px solid var(--color-danger);
}

.rule-card-header {
  margin-bottom: 10px;
  font-weight: 600;
}

.rule-tip {
  margin-top: 8px;
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.json-editor-desc {
  margin: 0 0 10px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.access-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  margin-top: 12px;
}

.access-card {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-subtle);
}

.access-card h3 {
  margin: 0 0 14px;
  font-size: 16px;
}

.kv-row {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed var(--color-border);
}

.kv-key {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.access-note {
  margin: 12px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.install-steps {
  margin: 0;
  padding-left: 20px;
  color: var(--color-text-primary);
  font-size: 13px;
  line-height: 2;
}

.endpoint-list {
  display: grid;
  gap: 8px;
}

.endpoint {
  display: grid;
  grid-template-columns: 64px auto 1fr;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.method {
  color: var(--color-primary);
  font-weight: 600;
}

.endpoint span {
  color: var(--color-text-secondary);
}
</style>
