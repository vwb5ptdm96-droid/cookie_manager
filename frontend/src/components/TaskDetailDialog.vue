<script setup lang="ts">
import type { SessionTaskItem } from "@/api/sessionTasks";

defineProps<{
  modelValue: boolean;
  task: SessionTaskItem | null;
  executing: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  execute: [];
}>();
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="任务详情"
    width="820px"
    @close="emit('update:modelValue', false)"
  >
    <div v-if="task" class="detail-grid">
      <section class="detail-card">
        <h3>基础信息</h3>
        <dl>
          <div><dt>任务编码</dt><dd>{{ task.task_code }}</dd></div>
          <div><dt>任务名称</dt><dd>{{ task.task_name }}</dd></div>
          <div><dt>渠道 / 手机号</dt><dd>{{ task.channel }} / {{ task.mobile_phone }}</dd></div>
          <div><dt>账号别名</dt><dd>{{ task.account_alias || "未填写" }}</dd></div>
          <div><dt>状态</dt><dd>{{ task.status }}</dd></div>
          <div><dt>运行频率</dt><dd>{{ task.schedule_value || task.schedule_type }}</dd></div>
        </dl>
      </section>

      <section class="detail-card">
        <h3>绑定信息</h3>
        <dl>
          <div><dt>Profile Key</dt><dd>{{ task.profile_key }}</dd></div>
          <div><dt>Profile 相对路径</dt><dd>{{ task.profile_relative_path }}</dd></div>
          <div><dt>Profile 绝对路径</dt><dd>{{ task.profile_absolute_path }}</dd></div>
          <div><dt>脚本</dt><dd>{{ task.script_name }} ({{ task.script_code }})</dd></div>
          <div><dt>脚本目录</dt><dd>{{ task.script_dir }}</dd></div>
          <div><dt>主文件</dt><dd>{{ task.script_main_file }}</dd></div>
        </dl>
      </section>

      <section class="detail-card full">
        <h3>DNS 与最近运行</h3>
        <p class="dns-list">{{ task.related_dns.join(", ") }}</p>
        <p class="meta-line">最近运行状态：{{ task.last_run_status || "尚未执行" }}</p>
        <p class="meta-line">最近执行时间：{{ task.last_run_at || "尚无记录" }}</p>
        <p class="meta-line">产物目录：{{ task.last_artifact_dir || "尚未生成" }}</p>
        <p v-if="task.last_error" class="error-line">最近错误：{{ task.last_error }}</p>
      </section>

      <section class="detail-card full">
        <h3>绑定健康检测</h3>
        <p class="meta-line">{{ task.health_check_codes.length ? task.health_check_codes.join(", ") : "当前未绑定健康检测" }}</p>
      </section>

      <section class="detail-card full">
        <h3>脚本配置</h3>
        <pre>{{ JSON.stringify(task.script_config, null, 2) }}</pre>
      </section>
    </div>

    <template #footer>
      <div class="dialog-actions">
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button type="primary" :loading="executing" @click="emit('execute')">执行脚本</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.detail-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-subtle);
}

.detail-card.full {
  grid-column: 1 / -1;
}

.detail-card h3 {
  margin: 0 0 12px;
}

dl {
  margin: 0;
  display: grid;
  gap: 10px;
}

dl div {
  display: grid;
  gap: 4px;
}

dt {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

dd,
.dns-list,
.meta-line,
.error-line {
  margin: 0;
  word-break: break-all;
}

pre {
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
}

.error-line {
  color: var(--color-danger);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 1023px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
