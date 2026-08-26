<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import QuickActionBar from "@/components/QuickActionBar.vue";

const route = useRoute();

const items = [
  { label: "健康检测任务", path: "/health-tasks" },
  { label: "Cookie 采集任务", path: "/cookie-sync-tasks" },
  { label: "脚本库", path: "/scripts" },
  { label: "目录库", path: "/profiles" },
  { label: "脚本运行", path: "/script-runs" },
  { label: "运行日志", path: "/logs" },
  { label: "环境自检", path: "/environment" },
  { label: "部署配置", path: "/deploy" },
];

const pageTitle = computed(() => String(route.meta.title ?? "Windows 原生 Session 健康检测与修复系统"));
const pageDescription = computed(() =>
  String(route.meta.description ?? "配置健康检测任务、追踪脚本运行，并在失败时自动修复或提醒。"),
);
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">Session 维护系统</div>
      <p class="brand-sub">Windows 单机部署 · 本机 Playwright · 健康检测与自动修复</p>
      <nav class="nav-list" aria-label="主导航">
        <RouterLink
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          active-class="is-active"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>

    <main class="main-content">
      <header class="page-header">
        <div class="page-copy">
          <h1>{{ pageTitle }}</h1>
          <p>{{ pageDescription }}</p>
        </div>
        <QuickActionBar />
      </header>

      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 276px 1fr;
  background: var(--color-background);
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 24px 18px;
  background: var(--color-sidebar);
  color: var(--color-sidebar-text);
}

.brand {
  margin-bottom: 6px;
  font-size: 20px;
  font-weight: 700;
}

.brand-sub {
  margin: 0 0 24px;
  color: var(--color-text-inverse-muted);
  font-size: 12px;
  line-height: 1.55;
}

.nav-list {
  display: grid;
  gap: 6px;
}

.nav-link {
  border-radius: var(--radius-md);
  padding: 12px 14px;
  color: inherit;
  text-decoration: none;
  transition: background-color 140ms ease;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.08);
}

.nav-link.is-active {
  background: var(--color-primary);
  color: #fff;
}

.main-content {
  padding: 26px 32px 42px;
  min-width: 0;
  overflow-x: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.page-copy {
  max-width: 640px;
}

h1 {
  margin: 0 0 8px;
  font-size: 26px;
  line-height: 1.25;
}

p {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

@media (max-width: 1023px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    height: auto;
  }

  .page-header {
    flex-direction: column;
  }
}
</style>
