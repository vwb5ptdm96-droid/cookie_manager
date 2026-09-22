<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  fetchAgentStatus,
  fetchAgentChat,
  fetchAutoRepairTicket,
  fetchAutoRepairTickets,
  fetchOpsSummary,
  fetchSreExplain,
  deleteAutoRepairTicket,
  probeBackendHealth,
  purgeClosedTickets,
  recycleStaleRuns,
  restartBackend,
  runSreEnvCheck,
  sendAgentChat,
  type AgentEvent,
  type AgentStatus,
  type AutoRepairTicketItem,
  type ChatMessage,
  type OpsSummary,
} from "@/api/autoRepairTickets";

const loading = ref(false);
const sending = ref(false);
const tickets = ref<AutoRepairTicketItem[]>([]);
const status = ref<AgentStatus>({ counts: {}, headline: "Agent 空闲", phase: "idle" });
const summary = ref<OpsSummary | null>(null);
const current = ref<AutoRepairTicketItem | null>(null);
const events = ref<AgentEvent[]>([]);
const chat = ref<ChatMessage[]>([]);
const diffText = ref("");
const draft = ref("");
const logEl = ref<HTMLElement | null>(null);
const sreBusy = ref(false);
const sreNote = ref("");
const route = useRoute();
let timer: number | null = null;

function statusType(value: string): "success" | "warning" | "danger" | "info" {
  if (value === "SOLVED") return "success";
  if (value === "RUNNING" || value === "PENDING") return "warning";
  if (value === "FAILED" || value === "NEED_HUMAN") return "danger";
  return "info";
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    think: "思考",
    tool_call: "操作",
    screenshot: "截图",
    script_diff: "改脚本",
    recheck: "复检",
    status: "状态",
    usage: "用量",
  };
  return map[type] || type;
}

const liveTickets = computed(() =>
  tickets.value.filter((row) => row.status === "RUNNING" || row.status === "PENDING"),
);

const progressLabel = computed(() => {
  const row = current.value;
  if (!row) return "值班问答（只读，不改脚本）";
  if (row.status === "RUNNING") return "Agent 正在处理这张工单";
  if (row.status === "PENDING") return "已建单，等待 Agent 接入";
  if (row.status === "SOLVED") {
    return row.kind === "cookie_sync" ? "已修好（采集复检 PASS）" : "已修好（健康复检 PASS）";
  }
  if (row.status === "NEED_HUMAN") return "已停手，需要人工";
  return "本轮排障结束";
});

const composerPlaceholder = computed(() =>
  current.value
    ? current.value.kind === "cookie_sync"
      ? "追问本采集任务（不改映射）"
      : "追问这张工单（不改脚本），例如：为什么复检失败？"
    : "问今天的运行情况（只读）。重启/回收请用右侧确认按钮。",
);

const railRole = computed(() => {
  if (sreBusy.value) return "SRE · 确认闸";
  if (!current.value) return "Watcher";
  if (current.value.kind === "cookie_sync") return "Collector · 追问不改脚本";
  return "Repairer · 追问不改脚本";
});

async function loadList(): Promise<void> {
  loading.value = true;
  try {
    const [data, live, ops] = await Promise.all([
      fetchAutoRepairTickets(),
      fetchAgentStatus(),
      fetchOpsSummary(),
    ]);
    tickets.value = data.items;
    status.value = live;
    summary.value = ops;
    if (current.value && !data.items.some((row) => row.id === current.value?.id)) {
      current.value = null;
      events.value = [];
      diffText.value = "";
    }
    if (!current.value && !sending.value) {
      await loadWatcherChat();
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载 Agent 工单失败");
  } finally {
    loading.value = false;
  }
}

async function openTicket(row: AutoRepairTicketItem): Promise<void> {
  current.value = row;
  await refreshDetail();
  await nextTick();
  scrollBottom();
}

function clearTicket(): void {
  current.value = null;
  events.value = [];
  diffText.value = "";
  void loadWatcherChat();
}

async function loadWatcherChat(): Promise<void> {
  if (current.value || sending.value) return;
  try {
    const data = await fetchAgentChat();
    if (!current.value && !sending.value) {
      chat.value = data.items;
    }
  } catch {
    /* 无单历史读失败不挡发送 */
  }
}

async function refreshDetail(): Promise<void> {
  if (!current.value) return;
  try {
    const detail = await fetchAutoRepairTicket(current.value.id);
    current.value = detail;
    events.value = detail.events ?? [];
    chat.value = detail.chat ?? [];
    diffText.value = detail.diff ?? "";
    await nextTick();
    scrollBottom();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载工单详情失败");
  }
}

function scrollBottom(): void {
  const el = logEl.value;
  if (el) el.scrollTop = el.scrollHeight;
}

async function applyRouteSelection(): Promise<void> {
  const ticketId = Number(route.query.ticket);
  const shop = String(route.query.shop || route.query.keyword || "").trim();
  if (ticketId) {
    const row = tickets.value.find((item) => item.id === ticketId);
    if (row) {
      await openTicket(row);
      return;
    }
  }
  if (shop) {
    const row = tickets.value.find(
      (item) =>
        (item.shop_name || "").includes(shop) ||
        (item.ticket_code || "").includes(shop) ||
        (item.health_task_code || "").includes(shop),
    );
    if (row) await openTicket(row);
  }
}

async function send(): Promise<void> {
  const text = draft.value.trim();
  if (!text || sending.value) return;
  const ticketId =
    current.value && tickets.value.some((row) => row.id === current.value?.id)
      ? current.value.id
      : undefined;
  if (current.value && ticketId == null) {
    current.value = null;
    events.value = [];
    diffText.value = "";
  }
  sending.value = true;
  draft.value = "";
  chat.value = [...chat.value, { role: "user", text }];
  await nextTick();
  scrollBottom();
  try {
    let result;
    try {
      result = await sendAgentChat(text, ticketId);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "";
      if (ticketId != null && msg.includes("不存在")) {
        current.value = null;
        events.value = [];
        diffText.value = "";
        result = await sendAgentChat(text);
      } else {
        throw error;
      }
    }
    chat.value = result.items;
    await nextTick();
    scrollBottom();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "发送失败");
  } finally {
    sending.value = false;
  }
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    void send();
  }
}

function startPoll(): void {
  stopPoll();
  timer = window.setInterval(() => {
    void loadList();
    if (current.value?.status === "RUNNING" || current.value?.status === "PENDING") {
      void refreshDetail();
    }
  }, 4000);
}

function stopPoll(): void {
  if (timer != null) {
    window.clearInterval(timer);
    timer = null;
  }
}

async function handleExplain(): Promise<void> {
  try {
    const data = await fetchSreExplain();
    const health = data.health as { ok?: boolean; status_code?: number } | undefined;
    sreNote.value = `探活 ${health?.ok ? "OK" : "失败"} HTTP ${health?.status_code ?? "-"}`;
    ElMessage.success(sreNote.value);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "解释后端失败");
  }
}

async function handleEnvCheck(): Promise<void> {
  sreBusy.value = true;
  try {
    await runSreEnvCheck();
    ElMessage.success("环境自检已执行");
    await loadList();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "自检失败");
  } finally {
    sreBusy.value = false;
  }
}

async function handleRecycle(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "将回收超时僵死的 ScriptRun，并释放仍指向这些运行的 Profile 锁。不会重启后端。",
      "确认回收停滞运行",
      { type: "warning", confirmButtonText: "确认回收", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  sreBusy.value = true;
  try {
    const out = await recycleStaleRuns();
    sreNote.value = `已回收 ${out.reclaimed} 条停滞运行`;
    ElMessage.success(sreNote.value);
    await loadList();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "回收失败");
  } finally {
    sreBusy.value = false;
  }
}

async function waitHealth(timeoutMs = 60000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const probe = await probeBackendHealth();
      if (probe.ok) return true;
    } catch {
      /* still down */
    }
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }
  return false;
}

async function handleRestart(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "将结束 8081 上的后端进程并经计划任务重新拉起，服务会短暂中断。对话里说「重启」不会执行这一步。",
      "确认重启后端",
      { type: "error", confirmButtonText: "确认重启", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  sreBusy.value = true;
  try {
    const out = await restartBackend();
    if (out.dry_run) {
      sreNote.value = out.message || "干跑：未杀进程";
      ElMessage.success(sreNote.value);
      return;
    }
    sreNote.value = "已调度重启，正在探活…";
    const ok = await waitHealth();
    sreNote.value = ok ? "重启后 /api/health 探活成功" : "已调度重启，但探活超时";
    if (ok) ElMessage.success(sreNote.value);
    else ElMessage.warning(sreNote.value);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "重启失败");
  } finally {
    sreBusy.value = false;
  }
}

async function handleDeleteCurrent(): Promise<void> {
  const row = current.value;
  if (!row) return;
  if (row.status === "RUNNING") {
    ElMessage.warning("处理中的工单不能删");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `删除工单 ${row.ticket_code}（${row.shop_name || row.channel}），并清掉本单目录/日志。RUNNING 不能删。`,
      "确认删除工单",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    await deleteAutoRepairTicket(row.id);
    current.value = null;
    events.value = [];
    chat.value = [];
    ElMessage.success("已删除");
    await loadList();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败");
  }
}

async function handlePurgeHistory(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "删除所有已关闭工单（SOLVED / NEED_HUMAN / FAILED），并清本单产物。PENDING/RUNNING 保留。",
      "清理历史工单",
      { type: "warning", confirmButtonText: "确认清理", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    const out = await purgeClosedTickets();
    if (current.value && ["SOLVED", "NEED_HUMAN", "FAILED"].includes(current.value.status)) {
      current.value = null;
      events.value = [];
      chat.value = [];
    }
    ElMessage.success(`已清理 ${out.deleted} 张`);
    await loadList();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "清理失败");
  }
}

onMounted(() => {
  void loadList().then(() => applyRouteSelection());
  startPoll();
  if (String(route.query.sre || "") === "recycle") {
    void handleRecycle();
  }
});
watch(
  () => [route.query.ticket, route.query.shop, route.query.keyword, route.query.sre],
  () => {
    void applyRouteSelection();
    if (String(route.query.sre || "") === "recycle") {
      void handleRecycle();
    }
  },
);
onUnmounted(stopPoll);
</script>

<template>
  <section class="agent-page">
    <header class="agent-banner" :class="`is-${status.phase}`">
      <div class="pulse" v-if="status.phase === 'running'" />
      <div>
        <strong>{{ status.headline }}</strong>
        <p>
          处理中 {{ status.counts.RUNNING || 0 }} · 排队 {{ status.counts.PENDING || 0 }} ·
          已修好 {{ status.counts.SOLVED || 0 }} · 需人工 {{ status.counts.NEED_HUMAN || 0 }}
        </p>
        <p v-if="summary" class="hint">
          早报 {{ summary.as_of }} · 健康 FAIL {{ summary.health.fail }}/{{ summary.health.enabled }} ·
          采集 FAIL {{ summary.cookie_sync.fail }} · 运行中 {{ summary.script_runs.running }} ·
          持锁 {{ summary.profiles.locked }}
        </p>
      </div>
      <el-button size="small" @click="loadList">刷新</el-button>
      <el-button size="small" type="danger" plain @click="handlePurgeHistory">清理历史</el-button>
    </header>

    <div class="agent-grid">
      <aside class="sessions">
        <h3>工单</h3>
        <p class="hint" v-if="liveTickets.length">{{ liveTickets.length }} 个进行中，点开即可看过程</p>
        <p class="hint" v-else>当前没有进行中的排障单</p>
        <div v-if="summary?.attention?.length" class="attention">
          <strong>需要人看</strong>
          <RouterLink
            v-for="item in summary.attention"
            :key="item.title + item.reason"
            class="attention-link"
            :to="{ path: item.path, query: item.query }"
          >
            {{ item.title }} · {{ item.reason }}
          </RouterLink>
        </div>
        <div class="session-list">
          <button
            v-for="row in tickets"
            :key="row.id"
            class="session"
            :class="{ active: current?.id === row.id, live: row.status === 'RUNNING' }"
            @click="openTicket(row)"
          >
            <span class="dot" :class="row.status.toLowerCase()" />
            <span class="session-body">
              <strong>{{ row.shop_name || row.ticket_code }}</strong>
              <small>{{ row.kind === "cookie_sync" ? "采集" : "排障" }} · {{ row.channel }} · {{ row.status }}</small>
            </span>
          </button>
        </div>
      </aside>

      <section class="transcript">
        <div class="transcript-head">
          <div>
            <h3>{{ current ? current.ticket_code : "值班摘要" }}</h3>
            <p class="hint">{{ progressLabel }}</p>
          </div>
          <el-button v-if="current" size="small" text @click="clearTicket">退出本单</el-button>
          <el-tag v-if="current" :type="statusType(current.status)" size="small">{{ current.status }}</el-tag>
          <el-tag v-else size="small" type="info">Watcher</el-tag>
        </div>

        <div ref="logEl" class="log" v-loading="loading && !current && !chat.length">
          <template v-if="current">
            <article v-if="current.error_message" class="bubble system">
              <span class="who">触发</span>
              <pre>{{ current.error_message }}</pre>
            </article>
            <article v-for="(ev, idx) in events" :key="'e' + idx" class="bubble" :class="ev.type">
              <span class="who">{{ eventLabel(ev.type) }}</span>
              <pre>{{ ev.text }}</pre>
            </article>
          </template>
          <article v-for="(msg, idx) in chat" :key="'c' + idx" class="bubble" :class="msg.role">
            <span class="who">{{ msg.role === "user" ? "你" : "Agent" }}</span>
            <pre>{{ msg.text }}</pre>
          </article>
          <p v-if="current && !events.length && !chat.length" class="hint">这张工单还没有过程记录。可在下方追问（不改脚本）。</p>
          <p v-else-if="!current && !chat.length" class="hint empty">没有选中工单也可以问。例如：今天跑得怎么样？</p>
        </div>

        <form class="composer" @submit.prevent="send">
          <textarea
            v-model="draft"
            rows="2"
            :disabled="sending"
            :placeholder="composerPlaceholder"
            @keydown="onKey"
          />
          <el-button type="primary" :loading="sending" native-type="submit">发送</el-button>
        </form>
      </section>

      <aside class="rail">
        <h3>进度</h3>
        <el-tag size="small" class="role-tag">{{ railRole }}</el-tag>
        <template v-if="current">
          <dl>
            <dt>状态</dt><dd>{{ current.status }}</dd>
            <dt>渠道</dt><dd>{{ current.channel }} / {{ current.shop_name || "-" }}</dd>
            <dt>CDP</dt><dd>{{ current.cdp_port }}</dd>
            <dt>健康任务</dt><dd>{{ current.health_task_code || "-" }}</dd>
            <dt>唤起次数</dt><dd>{{ current.dispatch_count }}</dd>
          </dl>
          <div v-if="current.usage" class="usage">
            Token 输入 {{ current.usage.input_tokens }} / 输出 {{ current.usage.output_tokens }}
            <span v-if="current.usage.num_turns != null"> · {{ current.usage.num_turns }} 轮</span>
            <div v-if="current.usage.model">{{ current.usage.model }}</div>
          </div>
          <pre v-if="diffText" class="diff">{{ diffText }}</pre>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="current.status === 'RUNNING'"
            @click="handleDeleteCurrent"
          >删除本单</el-button>
        </template>
        <div class="sre-gate">
          <strong>SRE 闸</strong>
          <p class="hint">对话不能重启。回收/重启必须点确认。</p>
          <el-button size="small" :loading="sreBusy" @click="handleExplain">解释后端</el-button>
          <el-button size="small" :loading="sreBusy" @click="handleEnvCheck">跑环境自检</el-button>
          <el-button size="small" :loading="sreBusy" @click="handleRecycle">回收停滞运行</el-button>
          <el-button size="small" type="danger" :loading="sreBusy" @click="handleRestart">重启后端</el-button>
          <p v-if="sreNote" class="hint">{{ sreNote }}</p>
        </div>
        <p v-if="!current" class="hint">未选工单时右列是 Watcher 摘要闸；选中工单后仍可做 SRE。</p>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.agent-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  height: calc(100vh - 200px);
  min-height: 0;
  overflow: hidden;
}
.agent-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}
.agent-banner.is-running {
  border-color: var(--color-primary);
}
.agent-banner p {
  margin: 2px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 0 0 var(--color-primary);
  animation: pulse 1.4s infinite;
}
@keyframes pulse {
  70% { box-shadow: 0 0 0 8px transparent; }
}
.agent-grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 260px;
  gap: 12px;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  align-items: stretch;
}
.sessions, .transcript, .rail {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.sessions, .rail {
  padding: 14px;
  display: flex;
  flex-direction: column;
}
.session-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.attention {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
}
.attention-link {
  color: var(--color-primary);
  text-decoration: none;
}
.role-tag { margin-bottom: 10px; align-self: flex-start; }
.sre-gate {
  margin-top: 12px;
  display: grid;
  gap: 6px;
}
.session {
  display: flex;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 8px 6px;
  border-radius: 8px;
  cursor: pointer;
}
.session:hover, .session.active { background: rgba(127,127,127,0.12); }
.session.live { outline: 1px solid var(--color-primary); }
.session-body { display: grid; }
.session-body small { color: var(--color-text-secondary); font-size: 12px; }
.dot {
  width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; background: #888;
}
.dot.running, .dot.pending { background: #e6a23c; }
.dot.solved { background: #67c23a; }
.dot.failed, .dot.need_human { background: #f56c6c; }
.transcript {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
}
.transcript-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px 8px;
}
.log {
  overflow: auto;
  min-height: 0;
  padding: 8px 16px 16px;
}
.bubble {
  margin: 0 0 12px;
}
.bubble .who {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
.bubble pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.55;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(127,127,127,0.1);
}
.bubble.user pre { background: var(--color-primary); color: #fff; }
.bubble.tool_call pre, .bubble.script_diff pre { font-family: ui-monospace, monospace; font-size: 12px; }
.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}
.composer textarea {
  resize: none;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  padding: 8px 10px;
  font: inherit;
  background: transparent;
  color: inherit;
}
.hint { color: var(--color-text-secondary); font-size: 12px; margin: 4px 0 10px; }
.empty { padding: 48px 12px; text-align: center; }
.rail dl { display: grid; grid-template-columns: 72px 1fr; gap: 6px 8px; font-size: 13px; }
.rail dt { color: var(--color-text-secondary); }
.rail dd { margin: 0; }
.usage, .diff {
  margin-top: 12px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.rail { overflow: hidden; }
.rail .hint, .rail dl, .rail .usage { flex-shrink: 0; }
.diff { max-height: 240px; overflow: auto; flex: 1; min-height: 0; }
@media (max-width: 1100px) {
  .agent-grid { grid-template-columns: 1fr; }
}
</style>
