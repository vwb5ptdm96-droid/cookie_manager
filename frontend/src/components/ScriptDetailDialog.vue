<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import type { ScriptItem } from "@/api/scripts";
import { updateScript } from "@/api/scripts";

const props = defineProps<{ modelValue: boolean; script: ScriptItem | null }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [];
}>();

const form = reactive({
  script_name: "",
  script_type: "",
  platform: "",
  description: "",
});
const submitting = ref(false);

watch(
  () => props.script,
  (s) => {
    if (s) {
      form.script_name = s.script_name;
      form.script_type = s.script_type;
      form.platform = s.platform;
      form.description = s.description ?? "";
    }
  },
  { immediate: true },
);

async function handleSave(): Promise<void> {
  if (!props.script) return;
  submitting.value = true;
  try {
    await updateScript(props.script.script_code, {
      script_name: form.script_name.trim(),
      script_type: form.script_type.trim(),
      platform: form.platform.trim(),
      description: form.description.trim() || null,
    });
    ElMessage.success("脚本信息已更新");
    emit("saved");
    emit("update:modelValue", false);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑脚本"
    width="640px"
    @close="emit('update:modelValue', false)"
  >
    <template v-if="script">
      <section class="detail-section">
        <h3>基础信息</h3>
        <dl class="detail-list">
          <div>
            <dt>脚本编码</dt>
            <dd><code>{{ script.script_code }}</code></dd>
          </div>
          <div>
            <dt>脚本名称</dt>
            <dd><el-input v-model="form.script_name" size="small" /></dd>
          </div>
          <div>
            <dt>类型</dt>
            <dd><el-input v-model="form.script_type" size="small" placeholder="自定义类型" /></dd>
          </div>
          <div>
            <dt>平台</dt>
            <dd><el-input v-model="form.platform" size="small" placeholder="自定义平台" /></dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ script.enabled ? "ENABLED" : "DISABLED" }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ script.updated_at || "未知" }}</dd>
          </div>
        </dl>
      </section>

      <section class="detail-section">
        <h3>路径信息</h3>
        <dl class="detail-list">
          <div>
            <dt>脚本目录</dt>
            <dd><code>{{ script.script_dir }}</code></dd>
          </div>
          <div>
            <dt>主文件</dt>
            <dd><code>{{ script.main_file }}</code></dd>
          </div>
        </dl>
      </section>

      <section class="detail-section">
        <h3>说明</h3>
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选，写清楚脚本用途" />
      </section>
    </template>

    <template #footer>
      <div class="dialog-actions">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 14px;
  background: var(--color-surface-subtle);
}

.detail-section h3,
.detail-section p {
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

code {
  font-family: var(--font-family-mono);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
