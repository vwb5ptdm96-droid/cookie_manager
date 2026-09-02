<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { fetchProfiles, type ProfileItem } from "@/api/profiles";
import { fetchRepairTickets, openRepairBrowser, type RepairTicketItem } from "@/api/repairs";
import { fetchScripts, type ScriptItem } from "@/api/scripts";
import {
  createSessionTask,
  executeSessionTask,
  fetchSessionTasks,
  toggleSessionTask,
  updateSessionTask,
  type SessionTaskCreatePayload,
  type SessionTaskItem,
} from "@/api/sessionTasks";
import TaskDetailDialog from "@/components/TaskDetailDialog.vue";
import TaskFormDialog from "@/components/TaskFormDialog.vue";

const route = useRoute();
const router = useRouter();

const tasks = ref<SessionTaskItem[]>([]);
const profiles = ref<ProfileItem[]>([]);
const scripts = ref<ScriptItem[]>([]);
const tickets = ref<RepairTicketItem[]>([]);
const loading = ref(false);
const submitting = ref(false);
const executingTaskCode = ref<string | null>(null);
const openingTaskCode = ref<string | null>(null);
const togglingTaskCode = ref<string | null>(null);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const currentTask = ref<SessionTaskItem | null>(null);
const editingTask = ref<SessionTaskItem | null>(null);
const filters = reactive({
  status: "",
  keyword: "",
});

const riskCount = computed(() => tasks.value.filter((item) => item.status === "RISK").length);
const validCount = computed(() => tasks.value.filter((item) => item.status === "VALID").length);
const filteredTasks = computed(() =>
  tasks.value.filter((item) => {
    const statusMatched = !filters.status || item.status === filters.status;
    const keyword = filters.keyword.trim().toLowerCase();
    const keywordMatched =
      !keyword ||
      [
        item.task_name,
        item.task_code,
        item.channel,
        item.mobile_phone,
        item.account_alias || "",
        item.profile_key,
        item.script_name,
        item.script_code,
      ]
        .join(" ")
        .toLowerCase()
        .includes(keyword);

    return statusMatched && keywordMatched;
  }),
);

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "VALID") return "success";
  if (status === "RISK" || status === "EXPIRED") return "danger";
  if (status === "REFRESHING") return "warning";
  return "info";
}

function findActiveTicket(taskCode: string): RepairTicketItem | undefined {
  return tickets.value.find((item) => item.task_code === taskCode && item.status !== "CLOSED");
}

async function loadPageData(): Promise<void> {
  loading.value = true;
  try {
    const [taskData, profileData, scriptData, ticketData] = await Promise.all([
      fetchSessionTasks(),
      fetchProfiles(),
      fetchScripts(),
      fetchRepairTickets(),
    ]);
    tasks.value = taskData.items;
    profiles.value = profileData.items;
    scripts.value = scriptData.items;
    tickets.value = ticketData.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载维护任务失败");
  } finally {
    loading.value = false;
  }
}

function openCreateDialog(): void {
  editingTask.value = null;
  dialogVisible.value = true;
}

function openEditDialog(task: SessionTaskItem): void {
  editingTask.value = task;
  dialogVisible.value = true;
}

async function handleSubmit(payload: SessionTaskCreatePayload): Promise<void> {
  submitting.value = true;
  const isEditing = !!editingTask.value;
  try {
    if (isEditing && editingTask.value) {
      await updateSessionTask(editingTask.value.task_code, payload);
    } else {
      await createSessionTask(payload);
    }
    dialogVisible.value = false;
    editingTask.value = null;
    ElMessage.success(isEditing ? "维护任务已更新" : "维护任务已创建");
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : isEditing ? "更新任务失败" : "创建任务失败");
  } finally {
    submitting.value = false;
  }
}

async function handleExecute(task: SessionTaskItem): Promise<void> {
  executingTaskCode.value = task.task_code;
  try {
    const result = await executeSessionTask(task.task_code);
    currentTask.value = result;
    ElMessage.success(`任务执行完成，结果：${result.last_run_status || result.status}`);
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行任务失败");
  } finally {
    executingTaskCode.value = null;
  }
}

async function handleToggle(task: SessionTaskItem): Promise<void> {
  togglingTaskCode.value = task.task_code;
  try {
    await toggleSessionTask(task.task_code, !task.enabled);
    ElMessage.success(task.enabled ? "任务已停用" : "任务已启用");
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "切换任务状态失败");
  } finally {
    togglingTaskCode.value = null;
  }
}

async function handleOpenRepair(task: SessionTaskItem): Promise<void> {
  const ticket = findActiveTicket(task.task_code);
  if (!ticket) {
    ElMessage.warning("当前任务没有待处理的人工修复工单");
    return;
  }

  openingTaskCode.value = task.task_code;
  try {
    const result = await openRepairBrowser(ticket.ticket_code, null);
    ElMessage.success(`修复浏览器已打开，工单状态：${result.status}`);
    await loadPageData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "打开修复浏览器失败");
  } finally {
    openingTaskCode.value = null;
  }
}

function openDetail(task: SessionTaskItem): void {
  currentTask.value = task;
  detailVisible.value = true;
}

async function clearCreateQuery(): Promise<void> {
  const query = { ...route.query };
  delete query.create;
  await router.replace({ path: route.path, query });
}

watch(
  () => route.query.create,
  async (value) => {
    if (value === "1") {
      openCreateDialog();
      await clearCreateQuery();
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
        <span class="summary-label">任务总数</span>
        <strong class="summary-value">{{ tasks.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">有效任务</span>
        <strong class="summary-value">{{ validCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">风险任务</span>
        <strong class="summary-value">{{ riskCount }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>维护任务</h2>
          <p>创建、筛选、启停和手动执行维护脚本。命中 `RISK` 后可直接从这里打开人工修复浏览器。</p>
        </div>
        <el-button type="primary" @click="openCreateDialog">新增维护任务</el-button>
      </div>

      <div class="filters">
        <el-select v-model="filters.status" clearable placeholder="任务状态">
          <el-option label="INIT" value="INIT" />
          <el-option label="VALID" value="VALID" />
          <el-option label="EXPIRED" value="EXPIRED" />
          <el-option label="REFRESHING" value="REFRESHING" />
          <el-option label="RISK" value="RISK" />
          <el-option label="DISABLED" value="DISABLED" />
        </el-select>
        <el-input v-model="filters.keyword" clearable placeholder="搜索任务、手机号、Profile 或脚本" />
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="filteredTasks" row-key="task_code" empty-text="暂无维护任务。先注册 Profile 和上传脚本，再点击「新增维护任务」创建一条任务配置。">
        <el-table-column prop="task_name" label="任务名称" min-width="180" />
        <el-table-column label="运行频率" min-width="140">
          <template #default="{ row }">
            <span>{{ row.schedule_value || row.schedule_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="channel" label="渠道" min-width="120" />
        <el-table-column label="手机号 / 账号" min-width="180">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.mobile_phone }}</strong>
              <span>{{ row.account_alias || "未填写别名" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="涉及 DNS" min-width="180">
          <template #default="{ row }">
            <span>{{ row.related_dns.join(", ") }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="profile_key" label="Profile Key" min-width="140" />
        <el-table-column prop="profile_relative_path" label="Profile 相对路径" min-width="170" />
        <el-table-column label="维护脚本" min-width="180">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.script_name }}</strong>
              <span>{{ row.script_code }} · {{ row.script_type }} · {{ row.platform }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近执行时间" min-width="180">
          <template #default="{ row }">
            <span>{{ row.last_run_at || "尚未执行" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="360">
          <template #default="{ row }">
            <div class="actions">
              <el-button size="small" @click="openDetail(row)">详情</el-button>
              <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="!row.enabled"
                :loading="executingTaskCode === row.task_code"
                @click="handleExecute(row)"
              >
                执行脚本
              </el-button>
              <el-button
                size="small"
                plain
                :loading="openingTaskCode === row.task_code"
                @click="handleOpenRepair(row)"
              >
                打开修复浏览器
              </el-button>
              <el-button
                size="small"
                :loading="togglingTaskCode === row.task_code"
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

    <TaskFormDialog
      v-model="dialogVisible"
      :initial-value="editingTask"
      :profiles="profiles"
      :scripts="scripts"
      :submitting="submitting"
      @submit="handleSubmit"
    />
    <TaskDetailDialog
      v-model="detailVisible"
      :task="currentTask"
      :executing="!!currentTask && executingTaskCode === currentTask.task_code"
      @execute="currentTask && handleExecute(currentTask)"
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

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
