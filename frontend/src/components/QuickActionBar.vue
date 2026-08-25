<script setup lang="ts">
import { useGlobalQuickActions } from "@/composables/use-global-quick-actions";

const {
  openEnvironmentChecks,
  openScriptUpload,
} = useGlobalQuickActions();
</script>

<template>
  <div class="quick-action-bar">
    <el-button @click="openEnvironmentChecks">执行环境自检</el-button>
    <el-button type="primary" @click="openScriptUpload">上传脚本</el-button>
  </div>
</template>

<style scoped>
.quick-action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
