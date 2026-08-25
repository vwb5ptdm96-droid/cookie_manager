<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  cancelScriptRun,
  fetchRunningScriptRuns,
  fetchScriptRuns,
  getScriptRun,
  pauseScriptRun,
  readScriptRunLog,
  readScriptRunResult,
  resumeScriptRun,
  type ScriptRunItem,
} from "@/api/scriptRuns";

const loading = ref(false);
const runs = ref<ScriptRunItem[]>([]);
const statusFilter = ref("");
const logVisible = ref(false);
const resultVisible = ref(false);
const currentRun = ref<ScriptRunItem | null>(null);
const logContent = ref("");
const resultContent = ref("");
const polling = ref(false);

const runningCount = computed(() => runs.value.filter((r) => r.status === "RUNNING").length);
const pausedCount = computed(() => runs.value.filter((r) => r.status === "PAUSED").length);
const finishedCount = computed(() =>
  runs.value.filter((r) => ["SUCCESS", "FAIL", "RISK", "CANCELED"].includes(r.status)).length,
);

const statusOptions = ["PENDING", "RUNNING", "PAUSED", "CANCELING", "CANCELED", "SUCCESS", "FAIL", "RISK"];
const activeFilter = ref<string | null>(null);

function filterByStatus(status: string | null): void {
  activeFilter.value = status;
  statusFilter.value = status ?? "";
  void loadData();
}

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS") return "success";
  if (status === "RUNNING" || status === "PENDING") return "warning";
  if (status === "PAUSED") return "info";
  if (status === "FAIL" || status === "RISK") return "danger";
  if (status === "CANCELED") return "info";
  return "info";
}

const STATUS_LABELS: Record<string, string> = {
  PENDING: "待执行",
  RUNNING: "运行中",
  PAUSED: "已暂停",
  CANCELING: "取消中",
  CANCELED: "已取消",
  SUCCESS: "成功",
  FAIL: "失败",
  RISK: "有风险",
};

const RUN_MODE_LABELS: Record<string, string> = {
  HEADLESS: "无头模式",
  HEADED: "有头模式",
};

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

function runModeLabel(mode: string): string {
  return RUN_MODE_LABELS[mode] || mode || "脚本默认";
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m${sec}s`;
}

async function loadData(): Promise<void> {
  loading.value = true;
  try {
    const params: { status?: string } = {};
    if (statusFilter.value) params.status = statusFilter.value;
    const data = await fetchScriptRuns(params);
    runs.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载执行实例失败");
  } finally {
    loading.value = false;
  }
}

async function handlePause(run: ScriptRunItem): Promise<void> {
  try {
    await pauseScriptRun(run.run_id);
    ElMessage.success("脚本已暂停");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "暂停失败");
  }
}

async function handleResume(run: ScriptRunItem): Promise<void> {
  try {
    await resumeScriptRun(run.run_id);
    ElMessage.success("脚本已继续");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "继续失败");
  }
}

async function handleCancel(run: ScriptRunItem): Promise<void> {
  try {
    await ElMessageBox.confirm("确认取消当前脚本执行？系统将终止进程树（包括脚本和可能拉起的浏览器进程）。", "取消执行", {
      type: "warning",
      confirmButtonText: "确认取消",
      cancelButtonText: "返回",
    });
  } catch {
    return;
  }
  try {
    await cancelScriptRun(run.run_id);
    ElMessage.success("脚本已取消");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "取消失败");
  }
}

async function openLog(run: ScriptRunItem): Promise<void> {
  currentRun.value = run;
  logContent.value = "";
  logVisible.value = true;
  await refreshLog();
}

async function refreshLog(): Promise<void> {
  if (!currentRun.value) return;
  try {
    const data = await readScriptRunLog(currentRun.value.run_id);
    logContent.value = data.content;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "读取日志失败");
  }
}

function startPolling(): void {
  polling.value = true;
  const interval = window.setInterval(async () => {
    if (!logVisible.value) {
      clearInterval(interval);
      polling.value = false;
      return;
    }
    await refreshLog();
  }, 3000);
}

async function openResult(run: ScriptRunItem): Promise<void> {
  try {
    const data = await readScriptRunResult(run.run_id);
    resultContent.value = JSON.stringify(data, null, 2);
    resultVisible.value = true;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "读取结果失败");
  }
}

onMounted(loadData);
</script>

<template>
  <section class="page-grid">
    <div class="summary-grid">
      <article class="summary-card" :class="{ active: activeFilter === 'RUNNING' }" @click="filterByStatus('RUNNING')">
        <span class="summary-label">运行中</span>
        <strong class="summary-value">{{ runningCount }}</strong>
      </article>
      <article class="summary-card" :class="{ active: activeFilter === 'PAUSED' }" @click="filterByStatus('PAUSED')">
        <span class="summary-label">已暂停</span>
        <strong class="summary-value">{{ pausedCount }}</strong>
      </article>
      <article class="summary-card" :class="{ active: activeFilter === null }" @click="filterByStatus(null)">
        <span class="summary-label">全部</span>
        <strong class="summary-value">{{ runs.length }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>脚本执行实例</h2>
          <p>查看所有脚本执行记录，包括当前运行中、已暂停和已完成的实例。支持暂停、继续和取消正在执行的脚本。</p>
        </div>
        <div class="toolbar-actions">
          <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 160px" @change="loadData">
            <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
          </el-select>
          <el-button :loading="loading" @click="loadData">刷新</el-button>
        </div>
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="runs" row-key="run_id" empty-text="暂无脚本执行记录。执行健康检测任务的修复脚本后会自动生成。">
          <el-table-column prop="run_id" label="Run ID" min-width="180" />
          <el-table-column label="健康检测任务" min-width="140">
            <template #default="{ row }">
              <span>{{ row.health_task_name || row.health_task_code || "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="脚本" min-width="140">
            <template #default="{ row }">
              <span>{{ row.script_name || row.script_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="directory_key" label="启动目录" min-width="140" />
          <el-table-column label="运行模式" min-width="110">
            <template #default="{ row }">
              <span>{{ runModeLabel(row.run_mode) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="120">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" min-width="170">
            <template #default="{ row }">
              <span>{{ row.start_time || "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="运行时长" min-width="100">
            <template #default="{ row }">
              <span>{{ formatDuration(row.duration_ms) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="pid" label="PID" min-width="80" />
          <el-table-column label="操作" width="300" fixed="right">
            <template #default="{ row }">
              <div class="actions">
                <el-button size="small" @click="openLog(row)">日志</el-button>
                <el-button size="small" @click="openResult(row)">结果</el-button>
                <el-button
                  v-if="row.status === 'RUNNING'"
                  size="small"
                  @click="handlePause(row)"
                >暂停</el-button>
                <el-button
                  v-if="row.status === 'PAUSED'"
                  size="small"
                  type="success"
                  @click="handleResume(row)"
                >继续</el-button>
                <el-button
                  v-if="['RUNNING', 'PAUSED'].includes(row.status)"
                  size="small"
                  type="danger"
                  @click="handleCancel(row)"
                >取消</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 日志对话框 -->
    <el-dialog v-model="logVisible" title="执行日志" width="900px" top="5vh" @closed="polling = false">
      <template v-if="currentRun">
        <div class="log-meta">
          <span><strong>Run ID：</strong>{{ currentRun.run_id }}</span>
          <span><strong>脚本：</strong>{{ currentRun.script_name || currentRun.script_code }}</span>
          <span><strong>状态：</strong>{{ currentRun.status }}</span>
        </div>
        <div class="log-actions">
          <el-button size="small" @click="refreshLog">刷新日志</el-button>
          <el-button size="small" :loading="polling" @click="startPolling">实时轮询</el-button>
        </div>
        <pre class="log-viewer"><code>{{ logContent || "(无日志内容)" }}</code></pre>
      </template>
    </el-dialog>

    <!-- 结果对话框 -->
    <el-dialog v-model="resultVisible" title="result.json" width="700px">
      <pre class="result-viewer"><code>{{ resultContent || "{}" }}</code></pre>
    </el-dialog>
  </section>
</template>

<style scoped>
.page-grid,
.summary-grid {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-card {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.summary-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
}

.summary-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}

.panel {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.summary-label {
  display: block;
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 28px;
  line-height: 1.1;
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

.toolbar-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.log-meta {
  display: flex;
  gap: 20px;
  margin-bottom: 12px;
  font-size: 13px;
}

.log-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.log-viewer,
.result-viewer {
  margin: 0;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: var(--font-family-mono);
  font-size: 12px;
  line-height: 1.55;
  max-height: 600px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 1023px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
  .panel-header {
    flex-direction: column;
  }
}
</style>
