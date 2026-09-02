<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchDashboard, type DashboardCheckItem, type DashboardLogItem } from "@/api/dashboard";

const loading = ref(false);
const stats = ref({
  tasks: 0,
  profiles: 0,
  checks: 0,
  pending_repairs: 0,
});
const recentLogs = ref<DashboardLogItem[]>([]);
const recentChecks = ref<DashboardCheckItem[]>([]);

const cards = computed(() => [
  { label: "维护任务", value: String(stats.value.tasks), hint: "当前系统中登记的任务总数" },
  { label: "Profile 目录", value: String(stats.value.profiles), hint: "当前可管理的浏览器 Profile 数量" },
  { label: "健康检测", value: String(stats.value.checks), hint: "已配置的登录态检测规则数量" },
  { label: "待人工修复", value: String(stats.value.pending_repairs), hint: "尚未关闭的风控工单数量" },
]);

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS" || status === "PASS") return "success";
  if (status === "RUNNING" || status === "VERIFYING" || status === "WARN") return "warning";
  if (status === "FAIL" || status === "FAILED" || status === "RISK") return "danger";
  return "info";
}

async function loadDashboard(): Promise<void> {
  loading.value = true;
  try {
    const data = await fetchDashboard();
    stats.value = data.stats;
    recentLogs.value = data.recent_logs;
    recentChecks.value = data.recent_checks;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载总览失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadDashboard);
</script>

<template>
  <section class="dashboard">
    <div class="stats-grid">
      <article v-for="item in cards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
        <p class="stat-hint">{{ item.hint }}</p>
      </article>
    </div>

    <div class="panel-grid">
      <section class="panel">
        <h2>当前主流程</h2>
        <ol class="process-list">
          <li>健康检测扫描旧 cookie 登录态，失败时触发绑定维护任务。</li>
          <li>维护任务执行脚本并更新任务状态、产物目录和运行日志。</li>
          <li>命中 `RISK` 时进入人工修复工单，由部署机桌面会话接管后再次复检。</li>
        </ol>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>最近日志</h2>
          <el-button size="small" :loading="loading" @click="loadDashboard">刷新</el-button>
        </div>
        <div v-if="recentLogs.length" class="stack-list">
          <article v-for="item in recentLogs" :key="`${item.run_id}-${item.created_at}`" class="event-card">
            <div class="event-head">
              <strong>{{ item.title }}</strong>
              <el-tag :type="statusType(item.status)" effect="plain">{{ item.status }}</el-tag>
            </div>
            <p>{{ item.message }}</p>
            <span>{{ item.run_type }} · {{ item.created_at }}</span>
          </article>
        </div>
        <el-empty v-else description="暂无运行日志。执行维护任务或健康检测后，日志会自动记录到这里。" />
      </section>
    </div>

    <section class="panel">
      <h2>最近健康检测</h2>
      <el-table
        v-loading="loading"
        :data="recentChecks"
        row-key="check_code"
        empty-text="暂无健康检测记录。配置检测规则后，执行结果会展示在这里。"
      >
        <el-table-column prop="check_name" label="检测名称" min-width="220" />
        <el-table-column prop="check_code" label="检测编码" min-width="170" />
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_result_message" label="最近结果" min-width="240" />
        <el-table-column prop="last_checked_at" label="最近检测时间" min-width="200" />
      </el-table>
    </section>
  </section>
</template>

<style scoped>
.dashboard,
.stats-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat-card,
.panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  padding: 18px;
}

.stat-label {
  display: block;
  margin-bottom: 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.stat-value {
  display: block;
  font-size: 30px;
  line-height: 1.1;
}

.stat-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.panel-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: 1.1fr 0.9fr;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.panel h2,
.panel p {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.process-list {
  margin: 0;
  padding-left: 20px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.stack-list {
  display: grid;
  gap: 12px;
}

.event-card {
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-subtle);
}

.event-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.event-card p {
  margin: 10px 0 8px;
  color: var(--color-text-primary);
}

.event-card span {
  color: var(--color-text-secondary);
  font-size: 12px;
}

@media (max-width: 1023px) {
  .stats-grid,
  .panel-grid {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
  }
}
</style>
