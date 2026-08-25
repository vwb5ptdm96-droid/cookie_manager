<script setup lang="ts">
import type { LogItem } from "@/api/logs";

defineProps<{
  modelValue: boolean;
  log: LogItem | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="日志详情"
    width="760px"
    @close="emit('update:modelValue', false)"
  >
    <template v-if="log">
      <div class="detail-grid">
        <section class="detail-section">
          <h3>基础信息</h3>
          <dl class="detail-list">
            <div>
              <dt>运行 ID</dt>
              <dd><code>{{ log.run_id }}</code></dd>
            </div>
            <div>
              <dt>类型</dt>
              <dd>{{ log.run_type }}</dd>
            </div>
            <div>
              <dt>任务 ID</dt>
              <dd>{{ log.task_id ?? "-" }}</dd>
            </div>
            <div>
              <dt>检测 ID</dt>
              <dd>{{ log.check_id ?? "-" }}</dd>
            </div>
            <div>
              <dt>工单 ID</dt>
              <dd>{{ log.ticket_id ?? "-" }}</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>{{ log.status }}</dd>
            </div>
            <div>
              <dt>时间</dt>
              <dd>{{ log.created_at }}</dd>
            </div>
          </dl>
        </section>

        <section class="detail-section">
          <h3>关联文件</h3>
          <dl class="detail-list">
            <div>
              <dt>日志文件</dt>
              <dd><code>{{ log.log_file_path || "未落盘" }}</code></dd>
            </div>
          </dl>
        </section>

        <section class="detail-section full">
          <h3>标题</h3>
          <p>{{ log.title }}</p>
        </section>

        <section class="detail-section full">
          <h3>消息</h3>
          <pre>{{ log.message }}</pre>
        </section>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-section {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-subtle);
}

.detail-section.full {
  grid-column: 1 / -1;
}

.detail-section h3,
.detail-section p,
pre {
  margin: 0;
}

.detail-section h3 {
  margin-bottom: 12px;
  font-size: 15px;
}

.detail-list {
  margin: 0;
  display: grid;
  gap: 12px;
}

.detail-list div {
  display: grid;
  gap: 4px;
}

dt {
  color: var(--color-text-secondary);
  font-size: 12px;
}

dd {
  margin: 0;
  color: var(--color-text-primary);
  word-break: break-all;
}

code,
pre {
  font-family: var(--font-family-mono);
}

pre {
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1023px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
