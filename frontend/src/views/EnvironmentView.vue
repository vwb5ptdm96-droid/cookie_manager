<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import {
  executeEnvironmentChecks,
  fetchLatestEnvironmentChecks,
  type EnvironmentCheckItem,
} from "@/api/environment";

const route = useRoute();
const router = useRouter();

const checks = ref<EnvironmentCheckItem[]>([]);
const loading = ref(false);
const running = ref(false);

const failCount = computed(() => checks.value.filter((item) => item.status === "FAIL").length);
const warnCount = computed(() => checks.value.filter((item) => item.status === "WARN").length);

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "PASS") return "success";
  if (status === "WARN") return "warning";
  if (status === "FAIL") return "danger";
  return "info";
}

async function loadLatest(): Promise<void> {
  loading.value = true;
  try {
    const data = await fetchLatestEnvironmentChecks();
    checks.value = data.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载环境自检结果失败");
  } finally {
    loading.value = false;
  }
}

async function runChecks(): Promise<void> {
  if (running.value) return;
  running.value = true;
  try {
    const data = await executeEnvironmentChecks();
    checks.value = data.items;
    ElMessage.success(`环境自检已完成，共 ${data.items.length} 项`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "执行环境自检失败");
  } finally {
    running.value = false;
  }
}

async function clearAutorunQuery(): Promise<void> {
  const query = { ...route.query };
  delete query.autorun;
  await router.replace({ path: route.path, query });
}

watch(
  () => route.query.autorun,
  async (value) => {
    if (value === "1") {
      await clearAutorunQuery();
      await runChecks();
    }
  },
  { immediate: true },
);

onMounted(loadLatest);
</script>

<template>
  <section class="page-grid">
    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">检查项总数</span>
        <strong class="summary-value">{{ checks.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">警告项</span>
        <strong class="summary-value">{{ warnCount }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">失败项</span>
        <strong class="summary-value">{{ failCount }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Windows 节点环境自检</h2>
          <p>重点确认运行目录、数据库、当前用户和桌面会话是否满足维护脚本与人工修复的前置条件。</p>
        </div>
        <div class="toolbar-actions">
          <el-button :loading="loading" @click="loadLatest">查看最近结果</el-button>
          <el-button type="primary" :loading="running" @click="runChecks">执行环境自检</el-button>
        </div>
      </div>

      <div v-loading="loading || running" class="check-grid">
        <article
          v-for="item in checks"
          :key="item.check_code"
          class="check-card"
          :class="`check-card--${item.status.toLowerCase()}`"
        >
          <div class="check-card__head">
            <span class="check-card__key">{{ item.check_code }}</span>
            <el-tag :type="statusType(item.status)" effect="plain">{{ item.status }}</el-tag>
          </div>
          <p class="check-card__summary">{{ item.summary }}</p>
          <span class="check-card__time">{{ item.created_at }}</span>
        </article>
        <el-empty v-if="!checks.length && !loading && !running" description="尚未执行环境自检。点击上方「执行环境自检」确认当前 Windows 节点是否满足部署条件。" />
      </div>

      <el-alert
        v-if="checks.length"
        type="info"
        :closable="false"
        show-icon
        class="deploy-hint"
        title="部署建议"
        description="如果桌面会话检查项为 WARN，请通过 RDP 登录部署机后再启动服务，确保人工修复浏览器可在桌面会话中正常打开。"
      />
    </section>
  </section>
</template>

<style scoped>
.page-grid,
.summary-grid {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-card,
.panel {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.summary-label {
  display: block;
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 28px;
  line-height: 1.1;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.panel-header h2,
.panel-header p {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.check-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.check-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.check-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.check-card__key {
  font-weight: 700;
  font-size: 14px;
}

.check-card__summary {
  margin: 0 0 8px;
  color: var(--color-text-primary);
  line-height: 1.6;
  word-break: break-word;
}

.check-card__time {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.check-card--pass {
  border-left: 3px solid var(--color-success);
}

.check-card--warn {
  border-left: 3px solid var(--color-warning);
}

.check-card--fail {
  border-left: 3px solid var(--color-danger);
}

.deploy-hint {
  margin-top: 16px;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 1023px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
  }
}
</style>
