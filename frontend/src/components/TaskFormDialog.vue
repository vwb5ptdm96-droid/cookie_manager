<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import type { ProfileItem } from "@/api/profiles";
import type { ScriptItem } from "@/api/scripts";
import type { SessionTaskCreatePayload, SessionTaskItem } from "@/api/sessionTasks";

const props = defineProps<{
  modelValue: boolean;
  submitting: boolean;
  profiles: ProfileItem[];
  scripts: ScriptItem[];
  initialValue?: SessionTaskItem | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: SessionTaskCreatePayload];
}>();

const formRef = ref<FormInstance>();
const form = reactive({
  task_name: "",
  channel: "KUAISHOU",
  mobile_phone: "",
  account_alias: "",
  related_dns_text: "s.kwaixiaodian.com",
  script_code: "",
  profile_key: "",
  schedule_type: "MANUAL",
  schedule_value: "manual",
  script_config_text: '{\n  "expected_status": "SUCCESS"\n}',
});

const rules: FormRules = {
  task_name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  channel: [{ required: true, message: "请输入渠道", trigger: "blur" }],
  mobile_phone: [{ required: true, message: "请输入手机号", trigger: "blur" }],
  script_code: [{ required: true, message: "请选择维护脚本", trigger: "change" }],
  profile_key: [{ required: true, message: "请选择 Profile", trigger: "change" }],
};

const dialogTitle = computed(() => (props.initialValue ? "编辑维护任务" : "新增维护任务"));
const submitLabel = computed(() => (props.initialValue ? "保存修改" : "保存任务"));
const scriptOptions = computed(() => props.scripts.filter((item) => item.script_type === "MAINTAIN" && item.enabled));

function resetForm(): void {
  form.task_name = "";
  form.channel = "KUAISHOU";
  form.mobile_phone = "";
  form.account_alias = "";
  form.related_dns_text = "s.kwaixiaodian.com";
  form.script_code = "";
  form.profile_key = "";
  form.schedule_type = "MANUAL";
  form.schedule_value = "manual";
  form.script_config_text = '{\n  "expected_status": "SUCCESS"\n}';
}

function applyInitialValue(task: SessionTaskItem | null | undefined): void {
  if (!task) {
    resetForm();
    return;
  }

  form.task_name = task.task_name;
  form.channel = task.channel;
  form.mobile_phone = task.mobile_phone;
  form.account_alias = task.account_alias || "";
  form.related_dns_text = task.related_dns.join(", ");
  form.script_code = task.script_code;
  form.profile_key = task.profile_key;
  form.schedule_type = task.schedule_type;
  form.schedule_value = task.schedule_value || "";
  form.script_config_text = JSON.stringify(task.script_config, null, 2);
}

watch(
  () => props.modelValue,
  (opened) => {
    if (opened) {
      applyInitialValue(props.initialValue);
      return;
    }

    resetForm();
  },
);

watch(
  () => props.initialValue,
  (value) => {
    if (props.modelValue) applyInitialValue(value);
  },
);

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return;
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.error("请先补全必填字段");
    return;
  }

  let scriptConfig: Record<string, unknown>;
  try {
    scriptConfig = JSON.parse(form.script_config_text) as Record<string, unknown>;
  } catch {
    ElMessage.error("脚本配置必须是合法 JSON");
    return;
  }

  const relatedDns = form.related_dns_text
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

  if (relatedDns.length === 0) {
    ElMessage.error("至少填写一个 DNS");
    return;
  }

  emit("submit", {
    task_name: form.task_name,
    channel: form.channel,
    mobile_phone: form.mobile_phone,
    account_alias: form.account_alias,
    related_dns: relatedDns,
    script_code: form.script_code,
    profile_key: form.profile_key,
    schedule_type: form.schedule_type,
    schedule_value: form.schedule_value,
    script_config: scriptConfig,
  });
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="720px"
    @close="emit('update:modelValue', false)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="task-form">
      <el-form-item label="任务名称" prop="task_name">
        <el-input v-model="form.task_name" placeholder="例如 快手店铺会话维护" />
      </el-form-item>
      <el-form-item label="渠道" prop="channel">
        <el-input v-model="form.channel" placeholder="例如 KUAISHOU" />
      </el-form-item>
      <el-form-item label="手机号" prop="mobile_phone">
        <el-input v-model="form.mobile_phone" placeholder="例如 13800000001" />
      </el-form-item>
      <el-form-item label="账号别名">
        <el-input v-model="form.account_alias" placeholder="例如 demo-shop" />
      </el-form-item>
      <el-form-item label="关联 DNS">
        <el-input
          v-model="form.related_dns_text"
          type="textarea"
          :rows="2"
          placeholder="多个 DNS 用逗号或换行分隔"
        />
      </el-form-item>
      <el-form-item label="维护脚本" prop="script_code">
        <el-select v-model="form.script_code" placeholder="选择 MAINTAIN 脚本">
          <el-option
            v-for="script in scriptOptions"
            :key="script.script_code"
            :label="`${script.script_name} (${script.platform})`"
            :value="script.script_code"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="Profile" prop="profile_key">
        <el-select v-model="form.profile_key" placeholder="选择 Profile">
          <el-option
            v-for="profile in profiles"
            :key="profile.profile_key"
            :label="`${profile.profile_key} · ${profile.relative_path}`"
            :value="profile.profile_key"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="运行频率类型">
        <el-input v-model="form.schedule_type" placeholder="MANUAL / INTERVAL" />
      </el-form-item>
      <el-form-item label="运行频率">
        <el-input v-model="form.schedule_value" placeholder="manual" />
      </el-form-item>
      <el-form-item label="脚本配置 JSON">
        <el-input v-model="form.script_config_text" type="textarea" :rows="8" />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-actions">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ submitLabel }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.task-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.task-form :deep(.el-form-item:last-child),
.task-form :deep(.el-form-item:nth-last-child(2)) {
  grid-column: 1 / -1;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 1023px) {
  .task-form {
    grid-template-columns: 1fr;
  }
}
</style>
