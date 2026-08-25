<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  closeRepairTicket,
  fetchRepairTickets,
  openRepairBrowser,
  verifyRepairTicket,
  type RepairTicketItem,
} from "@/api/repairs";
import RepairGuideDialog from "@/components/RepairGuideDialog.vue";

const tickets = ref<RepairTicketItem[]>([]);
const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const currentTicket = ref<RepairTicketItem | null>(null);

const pendingCount = computed(() =>
  tickets.value.filter((item) => ["OPEN", "WAIT_RDP_REPAIR", "BROWSER_OPENED", "VERIFYING", "FAILED"].includes(item.status)).length,
);
const closedCount = computed(() => tickets.value.filter((item) => item.status === "CLOSED").length);
const browserOpenedCount = computed(() => tickets.value.filter((item) => item.status === "BROWSER_OPENED").length);

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "CLOSED") return "success";
  if (status === "BROWSER_OPENED" || status === "VERIFYING") return "warning";
  if (status === "FAILED") return "danger";
  if (status === "OPEN" || status === "WAIT_RDP_REPAIR") return "info";
  return "danger";
}

async function loadTickets(): Promise<void> {
  loading.value = true;
  try {
    const data = await fetchRepairTickets();
    tickets.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载人工修复工单失败");
  } finally {
    loading.value = false;
  }
}

function openGuide(ticket: RepairTicketItem): void {
  currentTicket.value = ticket;
  dialogVisible.value = true;
}

async function handleOpen(payload: { ticketCode: string; repairedBy: string | null }): Promise<void> {
  submitting.value = true;
  try {
    const result = await openRepairBrowser(payload.ticketCode, payload.repairedBy);
    currentTicket.value = result;
    await loadTickets();
    ElMessage.success(`修复浏览器已打开，当前状态：${result.status}`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "打开修复浏览器失败");
  } finally {
    submitting.value = false;
  }
}

async function handleVerify(payload: { ticketCode: string; repairedBy: string | null }): Promise<void> {
  submitting.value = true;
  try {
    const result = await verifyRepairTicket(payload.ticketCode, payload.repairedBy);
    currentTicket.value = result;
    await loadTickets();
    ElMessage.success(`复检已完成，当前状态：${result.status}`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行复检失败");
  } finally {
    submitting.value = false;
  }
}

async function handleCloseTicket(payload: { ticketCode: string; repairedBy: string | null }): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "关闭工单不会把任务恢复为可用状态，系统会保留当前风险状态和日志。确认继续吗？",
      "关闭工单",
      {
        type: "warning",
        confirmButtonText: "确认关闭",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const result = await closeRepairTicket(payload.ticketCode, payload.repairedBy);
    currentTicket.value = result;
    await loadTickets();
    ElMessage.success("工单已关闭，任务仍保持风险状态");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "关闭工单失败");
  } finally {
    submitting.value = false;
  }
}

onMounted(loadTickets);
</script>

<template>
  <section class="page-grid">
    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">待处理工单</span>
        <strong class="summary-value">{{ pendingCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">已打开浏览器</span>
        <strong class="summary-value">{{ browserOpenedCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">已关闭工单</span>
        <strong class="summary-value">{{ closedCount }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>人工修复工单</h2>
          <p>这里只处理维护任务进入 `RISK` 之后的人工接管。先打开部署机浏览器，再完成人工验证，最后回到系统触发复检。</p>
        </div>
        <el-button @click="loadTickets">刷新工单</el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="tickets"
        row-key="ticket_code"
        empty-text="当前没有待处理工单，说明还没有任务进入人工修复链路。"
      >
        <el-table-column prop="ticket_code" label="工单号" min-width="170" />
        <el-table-column label="任务 / Profile" min-width="220">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.task_name }}</strong>
              <span>{{ row.profile_key }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风险信息" min-width="220">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.risk_type }}</strong>
              <span>{{ row.risk_message }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="140">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处理记录" min-width="220">
          <template #default="{ row }">
            <div class="meta-stack">
              <strong>{{ row.repaired_by || "未登记处理人" }}</strong>
              <span>打开：{{ row.browser_opened_at || "未打开" }}</span>
              <span>关闭：{{ row.closed_at || "未关闭" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="openGuide(row)">处理工单</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <RepairGuideDialog
      v-model="dialogVisible"
      :ticket="currentTicket"
      :submitting="submitting"
      @open="handleOpen"
      @verify="handleVerify"
      @close-ticket="handleCloseTicket"
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

.meta-stack {
  display: grid;
  gap: 4px;
}

.meta-stack span {
  color: var(--color-text-secondary);
  font-size: 12px;
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
