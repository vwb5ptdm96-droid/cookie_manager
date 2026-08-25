<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { RepairTicketItem } from "@/api/repairs";

const props = defineProps<{
  modelValue: boolean;
  ticket: RepairTicketItem | null;
  submitting: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  open: [payload: { ticketCode: string; repairedBy: string | null }];
  verify: [payload: { ticketCode: string; repairedBy: string | null }];
  closeTicket: [payload: { ticketCode: string; repairedBy: string | null }];
}>();

const repairedBy = ref("");

const canOpenBrowser = computed(() => {
  const status = props.ticket?.status;
  return status === "OPEN" || status === "WAIT_RDP_REPAIR" || status === "FAILED";
});

const canVerify = computed(() => {
  const status = props.ticket?.status;
  return status === "BROWSER_OPENED" || status === "VERIFYING";
});

const canCloseTicket = computed(() => props.ticket !== null && props.ticket.status !== "CLOSED");

watch(
  () => props.ticket,
  (ticket) => {
    repairedBy.value = ticket?.repaired_by ?? "";
  },
  { immediate: true },
);

function handleClose(): void {
  emit("update:modelValue", false);
}

function submitOpen(): void {
  if (!props.ticket) return;
  emit("open", { ticketCode: props.ticket.ticket_code, repairedBy: repairedBy.value.trim() || null });
}

function submitVerify(): void {
  if (!props.ticket) return;
  emit("verify", { ticketCode: props.ticket.ticket_code, repairedBy: repairedBy.value.trim() || null });
}

function submitCloseTicket(): void {
  if (!props.ticket) return;
  emit("closeTicket", { ticketCode: props.ticket.ticket_code, repairedBy: repairedBy.value.trim() || null });
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="人工修复指引"
    width="720px"
    destroy-on-close
    @close="handleClose"
  >
    <template v-if="ticket">
      <section class="dialog-grid">
        <div class="info-card risk-card">
          <span class="card-label">风险说明</span>
          <strong class="card-title">{{ ticket.risk_type }}</strong>
          <p>{{ ticket.risk_message || "当前任务命中了风控，需要在部署机桌面会话中人工接管。" }}</p>
        </div>

        <div class="info-card">
          <span class="card-label">工单定位</span>
          <dl class="info-list">
            <div><dt>工单号</dt><dd>{{ ticket.ticket_code }}</dd></div>
            <div><dt>任务</dt><dd>{{ ticket.task_name }}</dd></div>
            <div><dt>Profile</dt><dd>{{ ticket.profile_key }}</dd></div>
            <div><dt>Profile 路径</dt><dd class="mono">{{ ticket.profile_path || "未知" }}</dd></div>
            <div><dt>状态</dt><dd>{{ ticket.status }}</dd></div>
          </dl>
        </div>

        <div class="info-card">
          <span class="card-label">处理步骤</span>
          <ol class="steps">
            <li>先点击“打开修复浏览器”，系统会锁定当前 Profile，并在部署机桌面会话中拉起浏览器。</li>
            <li>通过 RDP 登录部署机，完成扫码、短信、验证码或设备确认等人工操作。</li>
            <li>处理完成后回到这里点击“我已完成，开始复检”，系统会解锁 Profile 并执行绑定健康检测。</li>
            <li>如果你决定本次不继续处理，可以直接关闭工单；系统会保留任务风险状态和日志，避免误判为已恢复。</li>
          </ol>
        </div>

        <div class="info-card">
          <span class="card-label">执行记录</span>
          <dl class="info-list">
            <div><dt>处理人</dt><dd>{{ ticket.repaired_by || "未填写" }}</dd></div>
            <div><dt>打开时间</dt><dd>{{ ticket.browser_opened_at || "尚未打开" }}</dd></div>
            <div><dt>关闭时间</dt><dd>{{ ticket.closed_at || "尚未关闭" }}</dd></div>
            <div><dt>产物目录</dt><dd class="mono">{{ ticket.browser_artifact_dir || "尚未生成" }}</dd></div>
          </dl>
        </div>

        <div class="info-card operator-card">
          <span class="card-label">处理人登记</span>
          <el-input
            v-model="repairedBy"
            maxlength="128"
            placeholder="填写当前处理人，便于追踪这次人工接管"
          />
        </div>
      </section>
    </template>

    <template #footer>
      <div class="footer-actions">
        <el-button @click="handleClose">关闭</el-button>
        <el-button
          v-if="canOpenBrowser"
          type="primary"
          :loading="submitting"
          @click="submitOpen"
        >
          打开修复浏览器
        </el-button>
        <el-button
          v-if="canVerify"
          type="success"
          :loading="submitting"
          @click="submitVerify"
        >
          我已完成，开始复检
        </el-button>
        <el-button
          v-if="canCloseTicket"
          type="danger"
          plain
          :loading="submitting"
          @click="submitCloseTicket"
        >
          关闭工单
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-grid {
  display: grid;
  gap: 16px;
}

.info-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.risk-card {
  border-color: color-mix(in srgb, var(--color-risk) 32%, white);
  background: color-mix(in srgb, var(--color-risk) 8%, white);
}

.operator-card {
  background: var(--color-surface-subtle);
}

.card-label {
  display: block;
  margin-bottom: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.card-title {
  display: block;
  margin-bottom: 8px;
}

.info-card p {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.info-list {
  display: grid;
  gap: 10px;
  margin: 0;
}

.info-list div {
  display: grid;
  gap: 4px;
}

.info-list dt {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.info-list dd {
  margin: 0;
}

.steps {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-primary);
  line-height: 1.7;
}

.mono {
  word-break: break-all;
  font-family: var(--font-family-mono);
  font-size: 12px;
}

.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
