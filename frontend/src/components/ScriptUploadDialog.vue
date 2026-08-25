<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import type { ScriptUploadPayload } from "@/api/scripts";
import { fetchProfiles, type ProfileItem } from "@/api/profiles";

const props = defineProps<{ modelValue: boolean; submitting: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: ScriptUploadPayload];
}>();


const profiles = ref<ProfileItem[]>([]);
const file = ref<File | null>(null);
const form = reactive({
  scriptName: "",
  scriptType: "MAINTAIN",
  platform: "COMMON",
  description: "",
  profileKey: null as string | null,
});

const fileName = computed(() => file.value?.name ?? "尚未选择 .py 脚本");

onMounted(loadProfiles);

async function loadProfiles(): Promise<void> {
  try {
    const data = await fetchProfiles();
    profiles.value = data.items;
  } catch {
    profiles.value = [];
  }
}

function resetForm(): void {
  file.value = null;
  form.scriptName = "";
  form.scriptType = "MAINTAIN";
  form.platform = "COMMON";
  form.description = "";
  form.profileKey = null;
}

watch(
  () => props.modelValue,
  (opened) => {
    if (opened) {
      void loadProfiles();
    } else {
      resetForm();
    }
  },
);

function handleFileChange(event: Event): void {
  const target = event.target as HTMLInputElement;
  file.value = target.files?.[0] ?? null;
}

function handleSubmit(): void {
  if (!file.value) return;
  emit("submit", {
    ...form,
    description: form.description.trim(),
    file: file.value,
  });
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="上传脚本"
    width="640px"
    @close="emit('update:modelValue', false)"
  >
    <section class="upload-card">
      <strong>上传规则</strong>
      <p>仅支持上传单个 `.py` 脚本文件。脚本编码和版本由系统自动管理。</p>

      <div class="form-grid">
        <label class="upload-field">
          <span class="upload-label">脚本名称</span>
          <input v-model.trim="form.scriptName" class="upload-input" type="text" placeholder="例如：快手维护脚本" />
        </label>
        <label class="upload-field">
          <span class="upload-label">脚本类型</span>
          <input v-model.trim="form.scriptType" class="upload-input" type="text" placeholder="例如：MAINTAIN" />
        </label>
        <label class="upload-field">
          <span class="upload-label">平台</span>
          <input v-model.trim="form.platform" class="upload-input" type="text" placeholder="例如：KUAISHOU" />
        </label>
        <label class="upload-field">
          <span class="upload-label">关联 Profile 目录（可选）</span>
          <select v-model="form.profileKey" class="upload-input">
            <option :value="null">不关联</option>
            <option v-for="p in profiles" :key="p.profile_key" :value="p.profile_key">{{ p.profile_key }}</option>
          </select>
        </label>
        <label class="upload-field upload-field--full">
          <span class="upload-label">说明</span>
          <textarea
            v-model="form.description"
            class="upload-input upload-textarea"
            rows="3"
            placeholder="可选，写明脚本用途或适用场景"
          ></textarea>
        </label>
      </div>

      <label class="upload-field">
        <span class="upload-label">选择脚本文件</span>
        <input class="upload-input" type="file" accept=".py" @change="handleFileChange" />
      </label>
      <code class="file-preview">{{ fileName }}</code>
    </section>

    <template #footer>
      <div class="dialog-actions">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button
          type="primary"
          :disabled="!file || !form.scriptName"
          :loading="submitting"
          @click="handleSubmit"
        >
          上传脚本
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.upload-card {
  display: grid;
  gap: 12px;
  padding: 18px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-subtle);
}

.upload-card p {
  margin: 0;
  color: var(--color-text-secondary);
}

.form-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.upload-field {
  display: grid;
  gap: 8px;
}

.upload-field--full {
  grid-column: 1 / -1;
}

.upload-textarea {
  resize: vertical;
  min-height: 88px;
}

.file-preview {
  display: block;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: #fff;
  color: var(--color-text-secondary);
}

.helper-text {
  font-size: 12px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 767px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
