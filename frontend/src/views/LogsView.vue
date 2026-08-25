<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute } from "vue-router";

import { fetchLogs, type LogFilters, type LogItem } from "@/api/logs";
import LogDetailDialog from "@/components/LogDetailDialog.vue";

const route = useRoute();
const loading = ref(false);
const logs = ref<LogItem[]>([]);
const detailVisible = ref(false);
const currentLog = ref<LogItem | null>(null);
const filters = reactive<LogFilters>({
  runType: "",
  status: "",
  taskId: "",
  checkId: "",
  ticketId: "",
  healthTaskCode: (route.query.health_task_code as string) || "",
  runId: "",
  keyword: "",
  startAt: "",
  endAt: "",
});

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS" || status === "PASS") return "success";
  if (status === "RUNNING" || status === "VERIFYING" || status === "WARN") return "warning";
  if (status === "FAIL" || status === "FAILED" || status === "RISK") return "danger";
  return "info";
}

async function loadLogs(): Promise<void> {
  loading.value = true;
  try {
    const data = await fetchLogs(filters);
    logs.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载运行日志失败");
  } finally {
    loading.value = false;
  }
}

function resetFilters(): void {
  filters.runType = "";
  filters.status = "";
  filters.taskId = "";
  filters.checkId = "";
  filters.ticketId = "";
  filters.healthTaskCode = "";
  filters.runId = "";
  filters.keyword = "";
  filters.startAt = "";
  filters.endAt = "";
  void loadLogs();
}

function openDetail(log: LogItem): void {
  currentLog.value = log;
  detailVisible.value = true;
}

function previewMessage(msg: string): string {
  if (!msg) return "-";
  // 取第一行，截取前 150 字符
  const firstLine = msg.split("\n")[0] || "";
  return firstLine.length > 150 ? firstLine.slice(0, 150) + "…" : firstLine;
}

onMounted(loadLogs);
</script>

<template>
  <section class="page-grid">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>运行日志</h2>
          <p>按类型、状态和关键字筛选任务、检测、修复等运行记录，用来定位最近一次失败发生在哪里。</p>
        </div>
      </div>

      <div class="filters">
        <el-select v-model="filters.runType" clearable placeholder="运行类型">
          <el-option label="TASK" value="TASK" />
          <el-option label="CHECK" value="CHECK" />
          <el-option label="REPAIR" value="REPAIR" />
          <el-option label="SCRIPT" value="SCRIPT" />
          <el-option label="PROFILE" value="PROFILE" />
          <el-option label="ENV" value="ENV" />
          <el-option label="SYSTEM" value="SYSTEM" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态">
          <el-option label="SUCCESS" value="SUCCESS" />
          <el-option label="PASS" value="PASS" />
          <el-option label="FAIL" value="FAIL" />
          <el-option label="FAILED" value="FAILED" />
          <el-option label="RISK" value="RISK" />
          <el-option label="WARN" value="WARN" />
          <el-option label="RUNNING" value="RUNNING" />
        </el-select>
        <el-input v-model="filters.taskId" clearable placeholder="任务 ID" />
        <el-input v-model="filters.checkId" clearable placeholder="检测 ID" />
        <el-input v-model="filters.ticketId" clearable placeholder="工单 ID" />
        <el-input v-model="filters.healthTaskCode" clearable placeholder="健康检测任务编码" />
        <el-input v-model="filters.runId" clearable placeholder="脚本运行 Run ID" />
        <el-input v-model="filters.keyword" clearable placeholder="输入关键字筛选标题或消息" />
        <el-input v-model="filters.startAt" clearable placeholder="开始时间 ISO，例如 2026-07-01T00:00:00" />
        <el-input v-model="filters.endAt" clearable placeholder="结束时间 ISO，例如 2026-07-01T23:59:59" />
        <div class="toolbar-actions">
          <el-button :loading="loading" @click="loadLogs">筛选日志</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <div class="table-shell">
        <el-table
        v-loading="loading"
        :data="logs"
        row-key="run_id"
        empty-text="暂无匹配的运行日志。尝试调整筛选条件，或在执行维护任务或健康检测后重新查看。"
      >
        <el-table-column prop="created_at" label="时间" min-width="180" />
        <el-table-column prop="run_type" label="类型" min-width="120" />
        <el-table-column prop="title" label="关联对象" min-width="180" />
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="消息" min-width="280">
          <template #default="{ row }">
            <div class="message-preview">{{ previewMessage(row.message) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="日志文件" min-width="220">
          <template #default="{ row }">
            <code>{{ row.log_file_path || "未落盘" }}</code>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </section>
    <LogDetailDialog v-model="detailVisible" :log="currentLog" />
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 16px 0;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.association-stack {
  display: grid;
  gap: 4px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.message-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-family: var(--el-font-family-mono, monospace);
}

code {
  word-break: break-all;
  font-family: var(--font-family-mono);
}

@media (max-width: 1023px) {
  .filters {
    grid-template-columns: 1fr;
  }
}
</style>
