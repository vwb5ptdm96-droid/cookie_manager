<script setup lang="ts">
import { reactive, ref, watch, computed } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import type { SessionTaskItem } from "@/api/sessionTasks";
import type { HealthCheckCreatePayload, HealthCheckItem } from "@/api/healthChecks";

const props = defineProps<{
  modelValue: boolean;
  submitting: boolean;
  tasks: SessionTaskItem[];
  initialValue?: HealthCheckItem | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: HealthCheckCreatePayload];
}>();

const formRef = ref<FormInstance>();
const form = reactive({
  check_name: "",
  cookie_table: "ods_cookie_playwright",
  channel: "KUAISHOU",
  shop_name: "",
  mobile_phone: "",
  dns: "s.kwaixiaodian.com",
  method: "GET",
  check_url: "",
  request_headers_text: '{\n  "X-Request": "health-check"\n}',
  request_body_text: "{}",
  success_rule_text: '{\n  "equals": {\n    "path": "status",\n    "value": "ok"\n  }\n}',
  failure_rule_text: '{\n  "equals": {\n    "path": "status",\n    "value": "expired"\n  }\n}',
  trigger_task_id: null as number | null,
});

const rules: FormRules = {
  check_name: [{ required: true, message: "请输入检测名称", trigger: "blur" }],
  channel: [{ required: true, message: "请输入渠道", trigger: "blur" }],
  shop_name: [{ required: true, message: "请输入店铺名称", trigger: "blur" }],
  mobile_phone: [{ required: true, message: "请输入手机号", trigger: "blur" }],
  dns: [{ required: true, message: "请输入 DNS", trigger: "blur" }],
  check_url: [{ required: true, message: "请输入检测 URL", trigger: "blur" }],
  trigger_task_id: [{ required: true, message: "请选择触发任务", trigger: "change" }],
};

const dialogTitle = computed(() => (props.initialValue ? "编辑健康检测" : "新增健康检测"));
const submitLabel = computed(() => (props.initialValue ? "保存修改" : "保存检测"));

function resetForm(): void {
  form.check_name = "";
  form.cookie_table = "ods_cookie_playwright";
  form.channel = "KUAISHOU";
  form.shop_name = "";
  form.mobile_phone = "";
  form.dns = "s.kwaixiaodian.com";
  form.method = "GET";
  form.check_url = "";
  form.request_headers_text = '{\n  "X-Request": "health-check"\n}';
  form.request_body_text = "{}";
  form.success_rule_text = '{\n  "equals": {\n    "path": "status",\n    "value": "ok"\n  }\n}';
  form.failure_rule_text = '{\n  "equals": {\n    "path": "status",\n    "value": "expired"\n  }\n}';
  form.trigger_task_id = null;
}

function applyInitialValue(check: HealthCheckItem | null | undefined): void {
  if (!check) {
    resetForm();
    return;
  }

  form.check_name = check.check_name;
  form.cookie_table = check.cookie_table;
  form.channel = check.channel;
  form.shop_name = check.shop_name;
  form.mobile_phone = check.mobile_phone;
  form.dns = check.dns;
  form.method = check.method;
  form.check_url = check.check_url;
  form.request_headers_text = JSON.stringify(check.request_headers, null, 2);
  form.request_body_text = JSON.stringify(check.request_body, null, 2);
  form.success_rule_text = JSON.stringify(check.success_rule, null, 2);
  form.failure_rule_text = JSON.stringify(check.failure_rule, null, 2);
  form.trigger_task_id = check.trigger_task_id;
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

function parseJson(text: string, fieldName: string): Record<string, unknown> {
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new Error(`${fieldName} 必须是合法 JSON`);
  }
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return;
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    ElMessage.error("请先补全必填字段");
    return;
  }

  try {
    emit("submit", {
      check_name: form.check_name,
      cookie_table: form.cookie_table,
      channel: form.channel,
      shop_name: form.shop_name,
      mobile_phone: form.mobile_phone,
      dns: form.dns,
      method: form.method,
      check_url: form.check_url,
      request_headers: parseJson(form.request_headers_text, "请求头"),
      request_body: parseJson(form.request_body_text, "请求体"),
      success_rule: parseJson(form.success_rule_text, "成功规则"),
      failure_rule: parseJson(form.failure_rule_text, "失败规则"),
      trigger_task_id: form.trigger_task_id as number,
    });
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "JSON 解析失败");
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="760px"
    @close="emit('update:modelValue', false)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="check-form">
      <el-form-item label="检测名称" prop="check_name">
        <el-input v-model="form.check_name" placeholder="例如 店铺主页登录态检测" />
      </el-form-item>
      <el-form-item label="旧 cookie 表">
        <el-input v-model="form.cookie_table" />
      </el-form-item>
      <el-form-item label="渠道" prop="channel">
        <el-input v-model="form.channel" />
      </el-form-item>
      <el-form-item label="店铺名称" prop="shop_name">
        <el-input v-model="form.shop_name" />
      </el-form-item>
      <el-form-item label="手机号" prop="mobile_phone">
        <el-input v-model="form.mobile_phone" />
      </el-form-item>
      <el-form-item label="DNS" prop="dns">
        <el-input v-model="form.dns" />
      </el-form-item>
      <el-form-item label="请求方法">
        <el-input v-model="form.method" />
      </el-form-item>
      <el-form-item label="检测 URL" prop="check_url">
        <el-input v-model="form.check_url" placeholder="http://127.0.0.1:9000/health" />
      </el-form-item>
      <el-form-item label="失败触发任务" prop="trigger_task_id">
        <el-select v-model="form.trigger_task_id" placeholder="选择失败后触发的维护任务">
          <el-option
            v-for="task in tasks"
            :key="task.id"
            :label="`${task.task_name} (${task.task_code})`"
            :value="task.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item class="full" label="请求头 JSON">
        <el-input v-model="form.request_headers_text" type="textarea" :rows="5" />
      </el-form-item>
      <el-form-item class="full" label="请求体 JSON">
        <el-input v-model="form.request_body_text" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item class="full" label="成功规则 JSON">
        <el-input v-model="form.success_rule_text" type="textarea" :rows="6" />
      </el-form-item>
      <el-form-item class="full" label="失败规则 JSON">
        <el-input v-model="form.failure_rule_text" type="textarea" :rows="6" />
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
.check-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.check-form :deep(.full) {
  grid-column: 1 / -1;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 1023px) {
  .check-form {
    grid-template-columns: 1fr;
  }
}
</style>
