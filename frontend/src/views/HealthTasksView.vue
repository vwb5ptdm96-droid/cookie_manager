<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { EditPen } from "@element-plus/icons-vue";
import { ArrowDown } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

import { fetchProfiles, type ProfileItem } from "@/api/profiles";
import { fetchScripts, type ScriptItem } from "@/api/scripts";
import {
  cloneHealthTask,
  createHealthTask,
  deleteHealthTask,
  executeHealthTaskCheck,
  executeHealthTaskRepair,
  fetchHealthTaskTimeline,
  fetchHealthTasks,
  toggleHealthTask,
  updateHealthTask,
  type HealthTaskCreatePayload,
  type HealthTaskItem,
  type HealthTaskUpdatePayload,
  type TimelineEntry,
} from "@/api/healthTasks";

const router = useRouter();

const tasks = ref<HealthTaskItem[]>([]);
const profiles = ref<ProfileItem[]>([]);
const scripts = ref<ScriptItem[]>([]);

const loading = ref(false);
const submitting = ref(false);
const checkingCode = ref<string | null>(null);
const repairingCode = ref<string | null>(null);
const togglingCode = ref<string | null>(null);
const dialogVisible = ref(false);
const editingTask = ref<HealthTaskItem | null>(null);
const timelineVisible = ref(false);
const timelineLoading = ref(false);
const timelineEntries = ref<TimelineEntry[]>([]);
const timelineTaskName = ref("");
const timelineDetailVisible = ref(false);
const timelineDetailContent = ref("");
const activeTab = ref("detect");

// ── JSON 编辑器 ──
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
  // 已经是 JSON
  try { JSON.parse(input); return { json: input }; } catch { /* 继续 */ }

  // Python/JS dict 格式：将单引号替换为双引号，同时处理值内的双引号
  let s = input.trim();
  try {
    // 1) 把值中的单引号字符串转成双引号，同时转义内部的双引号
    s = s.replace(/:\s*'((?:[^'\\]|\\.)*)'/g, (_m, content: string) => {
      return ': "' + content.replace(/"/g, '\\"') + '"';
    });
    // 2) 把键的单引号转成双引号
    s = s.replace(/'([^']+)'\s*:/g, '"$1":');
    // 3) 清理末尾逗号
    s = s.replace(/,\s*([}\]])/g, '$1');

    JSON.parse(s);
    return { json: s };
  } catch {
    return { json: input, error: "无法解析，请粘贴标准 JSON 或 Python 字典格式" };
  }
}

// ── 规则编辑器 ──
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

const filters = reactive({ status: "", keyword: "" });
const form = reactive<HealthTaskCreatePayload>({
  health_task_name: "",
  cookie_table: "ods_cookie_playwright",
  channel: "KUAISHOU",
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
  auto_repair_enabled: false,
  repair_cron_expression: null,
  repair_script_id: null,
  repair_directory_id: null,
  repair_run_mode: null,
  repair_script_config: null,
  repair_timeout_seconds: 600,
});

const filteredTasks = computed(() =>
  tasks.value.filter((item) => {
    const s = !filters.status || item.status === filters.status;
    const kw = filters.keyword.trim().toLowerCase();
    const m =
      !kw ||
      [item.health_task_name, item.health_task_code, item.channel, item.shop_name, item.dns, item.check_url]
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
};

function statusType(status: string): "success" | "danger" | "warning" | "info" {
  if (status === "PASS") return "success";
  if (status === "FAIL") return "danger";
  if (status === "PENDING") return "warning";
  return "info";
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

function shortTime(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      timeZone: "Asia/Shanghai",
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

async function loadData(): Promise<void> {
  loading.value = true;
  try {
    const [td, pd, sd] = await Promise.all([fetchHealthTasks(), fetchProfiles(), fetchScripts()]);
    tasks.value = td.items;
    profiles.value = pd.items;
    scripts.value = sd.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载数据失败");
  } finally {
    loading.value = false;
  }
}

function openCreate(): void {
  editingTask.value = null;
  Object.assign(form, {
    health_task_name: "",
    cookie_table: "ods_cookie_playwright",
    channel: "KUAISHOU",
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
    auto_repair_enabled: false,
    repair_cron_expression: null,
    repair_script_id: null,
    repair_directory_id: null,
    repair_run_mode: null,
    repair_script_config: null,
    repair_timeout_seconds: 600,
  });
  Object.assign(successRule, { ...ruleDefaults });
  Object.assign(failureRule, { ...ruleDefaults });
  activeTab.value = "detect";
  dialogVisible.value = true;
}

function openEdit(task: HealthTaskItem): void {
  editingTask.value = task;
  Object.assign(form, {
    health_task_name: task.health_task_name,
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
    auto_repair_enabled: task.auto_repair_enabled,
    repair_cron_expression: task.repair_cron_expression,
    repair_script_id: task.repair_script_id,
    repair_directory_id: task.repair_directory_id,
    repair_run_mode: task.repair_run_mode,
    repair_script_config: task.repair_script_config,
    repair_timeout_seconds: task.repair_timeout_seconds,
  });
  syncRulesFromForm();
  activeTab.value = "detect";
  dialogVisible.value = true;
}

async function handleSubmit(): Promise<void> {
  syncRulesToForm();
  submitting.value = true;
  try {
    if (editingTask.value) {
      await updateHealthTask(editingTask.value.health_task_code, form as HealthTaskUpdatePayload);
      ElMessage.success("健康检测任务已更新");
    } else {
      await createHealthTask(form as HealthTaskCreatePayload);
      ElMessage.success("健康检测任务已创建");
    }
    dialogVisible.value = false;
    editingTask.value = null;
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提交失败");
  } finally {
    submitting.value = false;
  }
}

async function handleCheck(task: HealthTaskItem): Promise<void> {
  checkingCode.value = task.health_task_code;
  try {
    const result = await executeHealthTaskCheck(task.health_task_code);
    const detail = (result as unknown as Record<string, string>).check_detail || "";
    await loadData();
    if (detail) {
      await ElMessageBox.alert(detail, `检测结果: ${result.status}`, {
        confirmButtonText: "确定",
        dangerouslyUseHTMLString: false,
        message: detail,
        customClass: "check-result-dialog",
      });
    } else {
      ElMessage.success(`检测完成，结果：${result.status}`);
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行检测失败");
  } finally {
    checkingCode.value = null;
  }
}

async function handleRepair(task: HealthTaskItem): Promise<void> {
  repairingCode.value = task.health_task_code;
  try {
    const result = await executeHealthTaskRepair(task.health_task_code);
    ElMessage.success(`修复执行完成，结果：${result.last_run_status || result.status}`);
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行修复失败");
  } finally {
    repairingCode.value = null;
  }
}

async function handleClone(task: HealthTaskItem): Promise<void> {
  try {
    await cloneHealthTask(task.health_task_code);
    ElMessage.success("任务已复制");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "复制失败");
  }
}

async function handleDelete(task: HealthTaskItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务「${task.health_task_name}」吗？关联的检测日志和执行记录也会一并删除。`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await deleteHealthTask(task.health_task_code);
    ElMessage.success("任务已删除");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败");
  }
}

async function handleToggle(task: HealthTaskItem): Promise<void> {
  togglingCode.value = task.health_task_code;
  try {
    await toggleHealthTask(task.health_task_code, !task.enabled);
    ElMessage.success(task.enabled ? "任务已停用" : "任务已启用");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "切换状态失败");
  } finally {
    togglingCode.value = null;
  }
}

function viewLogs(task: HealthTaskItem): void {
  router.push({ path: "/logs", query: { health_task_code: task.health_task_code } });
}

async function openTimeline(task: HealthTaskItem): Promise<void> {
  timelineTaskName.value = task.health_task_name;
  timelineEntries.value = [];
  timelineVisible.value = true;
  timelineLoading.value = true;
  try {
    timelineEntries.value = await fetchHealthTaskTimeline(task.health_task_code);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载执行记录失败");
  } finally {
    timelineLoading.value = false;
  }
}

function openTimelineDetail(detail: string): void {
  timelineDetailContent.value = detail;
  timelineDetailVisible.value = true;
}

function handleAction(cmd: string, task: HealthTaskItem): void {
  if (cmd === "repair") void handleRepair(task);
  else if (cmd === "logs") viewLogs(task);
  else if (cmd === "timeline") void openTimeline(task);
  else if (cmd === "clone") void handleClone(task);
  else if (cmd === "delete") void handleDelete(task);
  else if (cmd === "toggle") void handleToggle(task);
}

function profileDirName(id: number | null): string {
  if (id == null) return "-";
  return profiles.value.find((p) => p.id === id)?.profile_key ?? `#${id}`;
}

function scriptName(id: number | null): string {
  if (id == null) return "-";
  return scripts.value.find((s) => s.id === id)?.script_name ?? `#${id}`;
}

onMounted(loadData);
</script>

<template>
  <section class="page-grid">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>健康检测任务</h2>
          <p>配置旧 cookie 检测规则、高级调度和失败后自动修复。检测失败时自动执行维护脚本并写入新 cookie。</p>
        </div>
        <el-button type="primary" @click="openCreate">新增健康检测</el-button>
      </div>

      <div class="filters">
        <el-select v-model="filters.status" clearable placeholder="状态">
          <el-option label="PENDING" value="PENDING" />
          <el-option label="PASS" value="PASS" />
          <el-option label="FAIL" value="FAIL" />
          <el-option label="DISABLED" value="DISABLED" />
        </el-select>
        <el-input v-model="filters.keyword" clearable placeholder="搜索任务名称、渠道、店铺、DNS 或 API" />
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="filteredTasks" row-key="health_task_code" empty-text="暂无健康检测任务。点击「新增健康检测」创建一条任务。">
          <el-table-column prop="health_task_name" label="检测任务名称" min-width="180" />
          <el-table-column prop="cron_expression" label="调度" min-width="120">
            <template #default="{ row }">
              <code>{{ row.cron_expression || "手动" }}</code>
            </template>
          </el-table-column>
          <el-table-column label="失败执行脚本" min-width="140">
            <template #default="{ row }">
              <span>{{ scriptName(row.repair_script_id) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="自动修复" min-width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.auto_repair_enabled ? 'success' : 'info'" effect="plain" size="small">
                {{ row.auto_repair_enabled ? "开" : "关" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" effect="plain" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近检测" min-width="160">
            <template #default="{ row }">
              <span class="cell-muted">{{ formatBeijingTime(row.last_checked_at) || "尚未执行" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <div class="actions">
                <el-button size="small" @click="openEdit(row)">编辑</el-button>
                <el-button
                  size="small" type="primary"
                  :disabled="!row.enabled"
                  :loading="checkingCode === row.health_task_code"
                  @click="handleCheck(row)"
                >检测</el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => handleAction(cmd, row)">
                  <el-button size="small">
                    更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="timeline">执行记录</el-dropdown-item>
                      <el-dropdown-item
                        command="repair"
                        :disabled="!row.enabled || !row.auto_repair_enabled"
                      >执行修复脚本</el-dropdown-item>
                      <el-dropdown-item command="clone">复制</el-dropdown-item>
                      <el-dropdown-item command="logs">查看运行日志</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                      <el-dropdown-item
                        command="toggle"
                        :divided="true"
                      >{{ row.enabled ? "停用" : "启用" }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingTask ? '编辑健康检测任务' : '新增健康检测任务'"
      width="780px"
      @close="editingTask = null"
    >
      <el-tabs v-model="activeTab">
        <el-tab-pane label="检测配置" name="detect">
          <el-form label-width="140px" class="task-form">
            <!-- ── 区块1: 请求配置 ── -->
            <div class="form-section">
              <div class="form-section-title">请求配置</div>
              <el-form-item label="检测名称" required>
                <el-input v-model="form.health_task_name" placeholder="例如：快手订单接口检测" />
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
                    <el-input
                      v-model="form.http_headers"
                      placeholder="点击展开编辑"
                      readonly
                      @click="openJsonEditor('http_headers')"
                    >
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
                    <el-input
                      v-model="form.http_body"
                      placeholder="点击展开编辑"
                      readonly
                      @click="openJsonEditor('http_body')"
                    >
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

            <!-- ── 区块2: Cookie 数据源 ── -->
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

            <!-- ── 区块3: 判定规则 ── -->
            <div class="form-section">
              <div class="form-section-title">判定规则</div>
              <p class="form-section-desc">基于 HTTP 响应状态码和响应体判断。正则匹配对整个响应体（JSON 序列化后）进行搜索。不配置规则则默认状态码 2xx/3xx 为通过。</p>
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

        <el-tab-pane label="失败修复" name="repair">
          <el-form label-width="160px" class="task-form">
            <el-form-item label="失败后自动修复">
              <el-switch v-model="form.auto_repair_enabled" />
            </el-form-item>
            <el-form-item label="修复调度 cron">
              <el-input v-model="form.repair_cron_expression" placeholder="留空则不定时执行，例如 */30 * * * *" />
            </el-form-item>
            <el-form-item label="维护脚本">
              <el-select v-model="form.repair_script_id" clearable placeholder="选择脚本库中的脚本">
                <el-option
                  v-for="s in scripts"
                  :key="s.id"
                  :label="s.script_name"
                  :value="s.id"
                >
                  <span>{{ s.script_name }}</span>
                  <span class="option-hint"> — {{ s.script_code }}</span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="运行模式">
              <el-select v-model="form.repair_run_mode" clearable placeholder="使用脚本默认">
                <el-option label="使用脚本默认" :value="null" />
                <el-option label="无头模式" value="HEADLESS" />
                <el-option label="有头模式" value="HEADED" />
              </el-select>
            </el-form-item>
            <el-form-item label="脚本配置 JSON">
              <el-input v-model="form.repair_script_config" placeholder="可选，{}" />
            </el-form-item>
            <el-form-item label="执行超时(秒)">
              <el-input-number v-model="form.repair_timeout_seconds" :min="30" :max="86400" />
            </el-form-item>
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
        <p class="json-editor-desc">
          支持标准 JSON、Python 字典、JavaScript 对象格式。点击"格式化"自动转换。
        </p>
        <el-input
          v-model="jsonEditorTemp"
          type="textarea"
          :rows="14"
          placeholder="{
    'Content-Type': 'application/json',
    'Authorization': 'Bearer xxx',
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
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ editingTask ? "保存修改" : "创建任务" }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 执行时间线对话框 -->
    <el-dialog v-model="timelineVisible" :title="`执行记录 - ${timelineTaskName}`" width="760px" top="8vh">
      <div v-loading="timelineLoading" class="timeline">
        <div v-if="!timelineLoading && timelineEntries.length === 0" class="timeline-empty">
          暂无执行记录。执行检测或修复后会自动生成。
        </div>
        <div v-for="(entry, i) in timelineEntries" :key="i" class="timeline-item">
          <div class="timeline-dot" :class="entry.result === 'SUCCESS' || entry.result === 'PASS' ? 'dot-success' : entry.result === 'FAIL' ? 'dot-fail' : 'dot-warn'" />
          <div v-if="i < timelineEntries.length - 1" class="timeline-line" />
          <div class="timeline-body">
            <div class="timeline-header">
              <span class="timeline-action">{{ entry.action }}</span>
              <el-tag
                :type="entry.result === 'SUCCESS' || entry.result === 'PASS' ? 'success' : entry.result === 'FAIL' ? 'danger' : 'warning'"
                size="small"
                effect="plain"
              >{{ entry.result }}</el-tag>
              <span class="timeline-time">{{ shortTime(entry.time) }}</span>
            </div>
            <el-button v-if="entry.detail" size="small" @click="openTimelineDetail(entry.detail)">详情</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="timelineVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 时间线详情对话框 -->
    <el-dialog v-model="timelineDetailVisible" title="执行详情" width="700px" top="10vh">
      <pre class="detail-viewer"><code>{{ timelineDetailContent }}</code></pre>
      <template #footer>
        <el-button @click="timelineDetailVisible = false">关闭</el-button>
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
  margin-bottom: 16px;
}

.panel-header h2,
.panel-header p {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.filters {
  display: grid;
  gap: 12px;
  grid-template-columns: 200px minmax(240px, 1fr);
  margin-bottom: 16px;
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

.task-form {
  margin-top: 8px;
}

.option-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.form-item-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-left: 8px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 1023px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .panel-header {
    flex-direction: column;
  }
}

/* ── 表单区块 ── */
.form-section {
  border: 1px solid var(--color-border, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--color-bg, #fafafa);
}
.form-section-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border, #e4e7ed);
  color: var(--color-text-primary, #303133);
}
.form-section-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  margin: -6px 0 14px 0;
  line-height: 1.5;
}

/* ── 规则卡片 ── */
.rule-card {
  border: 1px solid var(--color-border, #e4e7ed);
  border-radius: 8px;
  padding: 14px;
  min-height: 180px;
}
.rule-card-success {
  border-left: 3px solid var(--el-color-success, #67c23a);
}
.rule-card-failure {
  border-left: 3px solid var(--el-color-danger, #f56c6c);
}
.rule-card-header {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
}
.rule-form {
  margin-top: 4px;
}
.rule-form .el-form-item {
  margin-bottom: 12px;
}
.rule-tip {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  text-align: center;
  padding: 16px 0;
}

/* ── JSON 编辑器 ── */
.json-editor-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  margin-bottom: 12px;
}

/* ── 可点击输入框 ── */
:deep(.el-input .el-input__inner[readonly]) {
  cursor: pointer;
}

/* ── 时间线 ── */
.timeline {
  position: relative;
  padding: 8px 0;
  min-height: 120px;
}

.timeline-empty {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 48px 0;
}

.timeline-item {
  display: flex;
  position: relative;
  padding-left: 28px;
  padding-bottom: 20px;
}

.timeline-item:last-child {
  padding-bottom: 0;
}

.timeline-dot {
  position: absolute;
  left: 0;
  top: 6px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid;
  background: var(--color-surface);
  z-index: 1;
}

.dot-success {
  border-color: var(--el-color-success);
}

.dot-fail {
  border-color: var(--el-color-danger);
}

.dot-warn {
  border-color: var(--el-color-warning);
}

.timeline-line {
  position: absolute;
  left: 5px;
  top: 20px;
  width: 2px;
  bottom: -4px;
  background: var(--color-border);
}

.timeline-body {
  flex: 1;
  min-width: 0;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.timeline-action {
  font-weight: 600;
  font-size: 14px;
}

.timeline-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.detail-viewer {
  margin: 0;
  padding: 10px 12px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
  font-family: var(--font-family-mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow: auto;
}
</style>
