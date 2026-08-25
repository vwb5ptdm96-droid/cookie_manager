<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { fetchHealthTaskTimeline, type TimelineEntry } from "@/api/healthTasks";

const props = defineProps<{
  modelValue: boolean;
  taskName: string;
  taskCode: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const entries = ref<TimelineEntry[]>([]);
const loading = ref(false);
const detailVisible = ref(false);
const detailContent = ref("");

watch(
  () => props.modelValue,
  (opened) => {
    if (opened) void loadTimeline();
    else {
      entries.value = [];
      detailVisible.value = false;
    }
  },
);

async function loadTimeline(): Promise<void> {
  entries.value = [];
  loading.value = true;
  try {
    entries.value = await fetchHealthTaskTimeline(props.taskCode);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载执行记录失败");
  } finally {
    loading.value = false;
  }
}

function openDetail(detail: string): void {
  detailContent.value = detail;
  detailVisible.value = true;
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
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="`执行记录 - ${taskName}`"
    width="760px"
    top="8vh"
    @close="emit('update:modelValue', false)"
  >
    <div v-loading="loading" class="timeline">
      <div v-if="!loading && entries.length === 0" class="timeline-empty">
        暂无执行记录。执行检测或修复后会自动生成。
      </div>
      <div v-for="(entry, i) in entries" :key="i" class="timeline-item">
        <div
          class="timeline-dot"
          :class="entry.result === 'SUCCESS' || entry.result === 'PASS' ? 'dot-success' : entry.result === 'FAIL' ? 'dot-fail' : 'dot-warn'"
        />
        <div v-if="i < entries.length - 1" class="timeline-line" />
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
          <el-button v-if="entry.detail" size="small" @click="openDetail(entry.detail)">详情</el-button>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="detailVisible" title="执行详情" width="700px" top="10vh">
    <pre class="detail-viewer"><code>{{ detailContent }}</code></pre>
    <template #footer>
      <el-button @click="detailVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.timeline {
  max-height: 56vh;
  overflow-y: auto;
  padding: 4px 0;
}

.timeline-empty {
  padding: 32px 0;
  text-align: center;
  color: #8a94a6;
  font-size: 13px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 18px;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}

.dot-success {
  background: #16a34a;
}

.dot-fail {
  background: #dc2626;
}

.dot-warn {
  background: #d97706;
}

.timeline-line {
  position: absolute;
  left: 4px;
  top: 16px;
  bottom: 0;
  width: 2px;
  background: #e5e7eb;
}

.timeline-body {
  flex: 1;
  min-width: 0;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.timeline-action {
  font-weight: 600;
  color: #1f2937;
}

.timeline-time {
  margin-left: auto;
  color: #8a94a6;
  font-size: 12px;
}

.detail-viewer {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 6px;
  padding: 14px;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
}
</style>
