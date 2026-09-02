<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import {
  createHealthCheck,
  executeAllHealthChecks,
  executeHealthCheck,
  fetchHealthChecks,
  toggleHealthCheck,
  updateHealthCheck,
  type HealthCheckCreatePayload,
  type HealthCheckItem,
} from "@/api/healthChecks";
import { fetchSessionTasks, type SessionTaskItem } from "@/api/sessionTasks";
import HealthCheckFormDialog from "@/components/HealthCheckFormDialog.vue";

const route = useRoute();
const router = useRouter();

const checks = ref<HealthCheckItem[]>([]);
const tasks = ref<SessionTaskItem[]>([]);
const loading = ref(false);
const submitting = ref(false);
const runningAll = ref(false);
const runningCode = ref<string | null>(null);
const togglingCode = ref<string | null>(null);
const dialogVisible = ref(false);
const editingCheck = ref<HealthCheckItem | null>(null);
const filters = reactive({
  status: "",
  keyword: "",
});

const passCount = computed(() => checks.value.filter((item) => item.status === "PASS").length);
const failCount = computed(() => checks.value.filter((item) => item.status === "FAIL").length);
const filteredChecks = computed(() =>
  checks.value.filter((item) => {
    const statusMatched = !filters.status || item.status === filters.status;
    const keyword = filters.keyword.trim().toLowerCase();
    const keywordMatched =
      !keyword ||
      [
        item.check_name,
        item.check_code,
        item.channel,
        item.shop_name,
        item.mobile_phone,
        item.dns,
        item.check_url,
        item.trigger_task_code || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(keyword);

    return statusMatched && keywordMatched;
  }),
);

function statusType(status: string): "success" | "danger" | "warning" | "info" {
  if (status === "PASS") return "success";
  if (status === "FAIL") return "danger";
  if (status === "PENDING") return "warning";
  return "info";
}

function formatRule(rule: Record<string, unknown>): string {
  return JSON.stringify(rule);
}

async function loadPageData(): Promise<void> {
  loading.value = true;
  try {
    const [checkData, taskData] = await Promise.all([fetchHealthChecks(), fetchSessionTasks()]);
    checks.value = checkData.items;
    tasks.value = taskData.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载健康检测失败");
  } finally {
    loading.value = false;
  }
}

function openCreateDialog(): void {
  editingCheck.value = null;
  dialogVisible.value = true;
}

function openEditDialog(check: HealthCheckItem): void {
  editingCheck.value = check;
  dialogVisible.value = true;
}

async function handleSubmit(payload: HealthCheckCreatePayload): Promise<void> {
  submitting.value = true;
  const isEditing = !!editingCheck.value;
  try {
    if (isEditing && editingCheck.value) {
      await updateHealthCheck(editingCheck.value.check_code, payload);
    } else {
      await createHealthCheck(payload);
    }
    dialogVisible.value = false;
    editingCheck.value = null;
    ElMessage.success(isEditing ? "健康检测已更新" : "健康检测已创建");
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : isEditing ? "更新检测失败" : "创建检测失败");
  } finally {
    submitting.value = false;
  }
}

async function handleExecute(check: HealthCheckItem): Promise<void> {
  runningCode.value = check.check_code;
  try {
    const result = await executeHealthCheck(check.check_code);
    ElMessage.success(`检测完成，结果：${result.status}`);
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行检测失败");
  } finally {
    runningCode.value = null;
  }
}

async function handleToggle(check: HealthCheckItem): Promise<void> {
  togglingCode.value = check.check_code;
  try {
    await toggleHealthCheck(check.check_code, !check.enabled);
    ElMessage.success(check.enabled ? "健康检测已停用" : "健康检测已启用");
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "切换检测状态失败");
  } finally {
    togglingCode.value = null;
  }
}

async function handleExecuteAll(): Promise<void> {
  if (runningAll.value) return;
  runningAll.value = true;
  try {
    const result = await executeAllHealthChecks();
    ElMessage.success(`已执行 ${result.items.length} 条健康检测`);
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "批量执行失败");
  } finally {
    runningAll.value = false;
  }
}

async function clearQueryFlag(flag: "create" | "runAll"): Promise<void> {
  const query = { ...route.query };
  delete query[flag];
  await router.replace({ path: route.path, query });
}

watch(
  () => route.query.create,
  async (value) => {
    if (value === "1") {
      openCreateDialog();
      await clearQueryFlag("create");
    }
  },
  { immediate: true },
);

watch(
  () => route.query.runAll,
  async (value) => {
    if (value === "1") {
      await clearQueryFlag("runAll");
      await handleExecuteAll();
    }
  },
  { immediate: true },
);

onMounted(loadPageData);
</script>

<template>
  <section class="page-grid">
    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">检测总数</span>
        <strong class="summary-value">{{ checks.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">通过</span>
        <strong class="summary-value">{{ passCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">失败</span>
        <strong class="summary-value">{{ failCount }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>健康检测</h2>
          <p>配置、筛选、启停和执行旧 cookie 检测规则，失败后可触发绑定维护任务。</p>
        </div>
        <div class="toolbar-actions">
          <el-button :loading="runningAll" @click="handleExecuteAll">执行全部健康检测</el-button>
          <el-button type="primary" @click="openCreateDialog">新增健康检测</el-button>
        </div>
      </div>

      <div class="filters">
        <el-select v-model="filters.status" clearable placeholder="检测状态">
          <el-option label="PENDING" value="PENDING" />
          <el-option label="PASS" value="PASS" />
          <el-option label="FAIL" value="FAIL" />
          <el-option label="DISABLED" value="DISABLED" />
        </el-select>
        <el-input v-model="filters.keyword" clearable placeholder="搜索检测名、店铺、手机号、DNS 或任务" />
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="filteredChecks" row-key="check_code" empty-text="暂无健康检测。点击「新增健康检测」配置旧 cookie 检测规则并绑定触发任务。">
        <el-table-column prop="check_name" label="检测名称" min-width="180" />
        <el-table-column prop="cookie_table" label="cookie 表" min-width="180" />
        <el-table-column label="定位信息" min-width="200">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.channel }} / {{ row.shop_name }}</strong>
              <span>{{ row.mobile_phone }} / {{ row.dns }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="检测 API" min-width="220">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.method }}</strong>
              <span>{{ row.check_url }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="成功规则" min-width="180">
          <template #default="{ row }">
            <code class="rule-text">{{ formatRule(row.success_rule) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="失败规则" min-width="180">
          <template #default="{ row }">
            <code class="rule-text">{{ formatRule(row.failure_rule) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="绑定任务" min-width="180">
          <template #default="{ row }">
            <span>{{ row.trigger_task_code || "未绑定任务" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近检测时间" min-width="180">
          <template #default="{ row }">
            <span>{{ row.last_checked_at || "尚未执行" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <div class="actions">
              <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="!row.enabled"
                :loading="runningCode === row.check_code"
                @click="handleExecute(row)"
              >
                执行检测
              </el-button>
              <el-button
                size="small"
                :loading="togglingCode === row.check_code"
                @click="handleToggle(row)"
              >
                {{ row.enabled ? "停用" : "启用" }}
              </el-button>
            </div>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </section>

    <HealthCheckFormDialog
      v-model="dialogVisible"
      :initial-value="editingCheck"
      :tasks="tasks"
      :submitting="submitting"
      @submit="handleSubmit"
    />
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

.summary-card,
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

.toolbar-actions,
.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.filters {
  display: grid;
  gap: 12px;
  grid-template-columns: 200px minmax(240px, 1fr);
  margin-bottom: 16px;
}

.meta-stack {
  display: grid;
  gap: 4px;
}

.meta-stack span {
  color: var(--color-text-secondary);
  font-size: 12px;
  word-break: break-all;
}

.rule-text {
  display: block;
  font-family: var(--font-family-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1023px) {
  .summary-grid,
  .filters {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
  }
}
</style>
