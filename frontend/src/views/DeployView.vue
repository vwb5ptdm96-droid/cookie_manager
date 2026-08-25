<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchDeployConfig, type DeployConfigPayload } from "@/api/deploy";

const loading = ref(false);
const config = ref<DeployConfigPayload | null>(null);

async function loadConfig(): Promise<void> {
  loading.value = true;
  try {
    config.value = await fetchDeployConfig();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载部署配置失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadConfig);
</script>

<template>
  <section class="page-grid">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>部署配置</h2>
          <p>这里只展示当前节点的部署约束、运行根目录和启动命令，不在页面内直接修改运行配置。</p>
        </div>
        <el-button :loading="loading" @click="loadConfig">刷新配置</el-button>
      </div>

      <template v-if="config">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          class="user-hint"
          :title="`当前运行用户：${config.current_user}`"
          :description="config.current_user_hint"
        />

        <div class="config-grid">
          <article class="config-card">
            <span class="config-label">部署根目录</span>
            <code>{{ config.deploy_root }}</code>
          </article>
          <article class="config-card">
            <span class="config-label">运行根目录</span>
            <code>{{ config.runtime_root }}</code>
          </article>
          <article class="config-card">
            <span class="config-label">启动命令</span>
            <code>{{ config.startup_command }}</code>
          </article>
          <article class="config-card">
            <span class="config-label">API 监听</span>
            <code>{{ config.api_host }}:{{ config.api_port }}</code>
          </article>
        </div>

        <section class="sub-panel">
          <h3>关键目录</h3>
          <dl class="directory-list">
            <div v-for="(value, key) in config.directories" :key="key">
              <dt>{{ key }}</dt>
              <dd><code>{{ value }}</code></dd>
            </div>
          </dl>
        </section>
      </template>

      <el-empty v-else description="尚未加载部署配置" />
    </section>
  </section>
</template>

<style scoped>
.page-grid {
  display: grid;
  gap: 16px;
}

.panel,
.config-card,
.sub-panel {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.panel-header h2,
.panel-header p,
.sub-panel h3 {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.user-hint {
  margin-bottom: 16px;
}

.config-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.config-card,
.sub-panel {
  padding: 16px;
}

.config-label {
  display: block;
  margin-bottom: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

code {
  display: block;
  word-break: break-all;
  font-family: var(--font-family-mono);
}

.sub-panel {
  margin-top: 16px;
}

.directory-list {
  display: grid;
  gap: 12px;
  margin: 12px 0 0;
}

.directory-list div {
  display: grid;
  gap: 4px;
}

.directory-list dt {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.directory-list dd {
  margin: 0;
}

@media (max-width: 1023px) {
  .config-grid {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
  }
}
</style>
