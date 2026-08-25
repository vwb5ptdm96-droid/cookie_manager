<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage, type FormRules, type FormInstance } from "element-plus";

import { apiRequest } from "@/api/http";
import type { ProfileItem, ProfileUpsertPayload } from "@/api/profiles";
import type { ScriptItem } from "@/api/scripts";
import FolderBrowserDialog from "@/components/FolderBrowserDialog.vue";

const props = defineProps<{
  modelValue: boolean;
  submitting: boolean;
  scripts: ScriptItem[];
  profile: ProfileItem | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: ProfileUpsertPayload, scriptCodes: string[]];
}>();

const formRef = ref<FormInstance>();
const form = reactive<ProfileUpsertPayload>({
  profile_key: "",
  relative_path: "",
  note: "",
});
const selectedScriptCodes = ref<string[]>([]);

function initSelections(): void {
  selectedScriptCodes.value = props.scripts
    .filter((s) => s.profile_key === form.profile_key)
    .map((s) => s.script_code);
}

const rules: FormRules<ProfileUpsertPayload> = {
  profile_key: [{ required: true, message: "请输入 Profile Key", trigger: "blur" }],
  relative_path: [{ required: true, message: "请选择目录", trigger: "blur" }],
};

const browserVisible = ref(false);
const profilesRoot = ref("");

onMounted(async () => {
  try {
    const data = await apiRequest<{ directories: { profiles: string } }>("/deploy/config");
    profilesRoot.value = data.directories.profiles;
  } catch {
    // 静默失败，文件浏览器从根目录开始
  }
});

function onFolderSelected(path: string): void {
  // 将绝对路径转换为相对于 runtime/profiles 的路径
  // 例如: E:\...\runtime\profiles\moren-chrome → profiles/moren-chrome
  if (profilesRoot.value) {
    const root = profilesRoot.value.replace(/\\/g, "/").replace(/\/$/, "");
    const selected = path.replace(/\\/g, "/").replace(/\/$/, "");
    if (selected.startsWith(root)) {
      form.relative_path = "profiles" + selected.slice(root.length);
      return;
    }
  }
  // 兜底：直接使用 profiles/ 前缀
  const name = path.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "profile";
  form.relative_path = "profiles/" + name;
}

watch(
  () => props.modelValue,
  (opened) => {
    if (opened && props.profile) {
      form.profile_key = props.profile.profile_key;
      form.relative_path = props.profile.relative_path;
      form.note = props.profile.note || "";
      initSelections();
    }
    if (!opened) {
      form.profile_key = "";
      form.relative_path = "";
      form.note = "";
      selectedScriptCodes.value = [];
    }
  },
);

watch(
  () => props.profile,
  (profile) => {
    if (profile && props.modelValue) {
      form.profile_key = profile.profile_key;
      form.relative_path = profile.relative_path;
      form.note = profile.note || "";
      initSelections();
    }
  },
);

watch(
  () => form.profile_key,
  () => {
    if (props.modelValue) initSelections();
  },
);

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return;
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.error("请先补全必填字段");
    return;
  }
  emit("submit", { ...form }, selectedScriptCodes.value);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="profile ? '编辑 Profile' : '登记 Profile'"
    width="640px"
    @close="emit('update:modelValue', false)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="Profile Key" prop="profile_key">
        <el-input v-model="form.profile_key" placeholder="例如 profile_ks_demo01" />
      </el-form-item>
      <el-form-item label="绑定脚本">
        <el-select v-model="selectedScriptCodes" multiple placeholder="选择要绑定的脚本" collapse-tags>
          <el-option
            v-for="script in props.scripts"
            :key="script.script_code"
            :label="script.script_name"
            :value="script.script_code"
          >
            <span>{{ script.script_name }}</span>
            <span v-if="selectedScriptCodes.includes(script.script_code)" style="float:right;color:var(--el-color-primary);margin-left:12px;">✓</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="目录路径" prop="relative_path">
        <div class="path-picker">
          <el-input v-model="form.relative_path" placeholder="点击浏览选择目录" readonly>
            <template #append>
              <el-button @click="browserVisible = true">浏览...</el-button>
            </template>
          </el-input>
        </div>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="3" placeholder="可记录来源、机器说明或绑定备注" />
      </el-form-item>
    </el-form>

    <FolderBrowserDialog v-model="browserVisible" :root-path="profilesRoot || undefined" @select="onFolderSelected" />

    <template #footer>
      <div class="dialog-actions">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ profile ? "更新 Profile" : "保存 Profile" }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.path-picker {
  width: 100%;
}

</style>
