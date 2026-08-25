<script setup lang="ts">
import { useGlobalQuickActions } from "@/composables/use-global-quick-actions";

const {
  openEnvironmentChecks,
  runAllHealthChecks,
  openTaskCreate,
  openCheckCreate,
  openScriptUpload,
} = useGlobalQuickActions();
</script>

<template>
  <div class="quick-action-bar">
    <el-button @click="openEnvironmentChecks">执行环境自检</el-button>
    <el-button @click="runAllHealthChecks">执行全部健康检测</el-button>
    <el-button type="primary" plain @click="openTaskCreate">新增维护任务</el-button>
    <el-button type="primary" plain @click="openCheckCreate">新增健康检测</el-button>
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
