<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { apiRequest } from "@/api/http";

interface FsItem {
  name: string;
  path: string;
  is_dir: boolean;
}

interface FsListResponse {
  current_path: string;
  parent_path: string | null;
  items: FsItem[];
}

const props = defineProps<{
  modelValue: boolean;
  rootPath?: string;
}>();
const emit = defineEmits<{
  select: [path: string];
  "update:modelValue": [value: boolean];
}>();

const currentPath = ref("");
const parentPath = ref<string | null>(null);
const items = ref<FsItem[]>([]);
const loading = ref(false);
const selectedPath = ref("");

async function loadDirectory(path: string): Promise<void> {
  loading.value = true;
  try {
    const data = await apiRequest<FsListResponse>(`/fs/list?path=${encodeURIComponent(path)}`);
    currentPath.value = data.current_path;
    // 如果有 rootPath 限制，父路径不能高于 rootPath
    parentPath.value = data.parent_path;
    if (props.rootPath && parentPath.value) {
      const root = props.rootPath.replace(/\\/g, "/").replace(/\/$/, "");
      const parent = parentPath.value.replace(/\\/g, "/").replace(/\/$/, "");
      if (!parent.startsWith(root)) {
        parentPath.value = null;
      }
    }
    items.value = data.items;
    selectedPath.value = "";
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载目录失败");
  } finally {
    loading.value = false;
  }
}

function openDirectory(item: FsItem): void {
  if (item.is_dir) {
    loadDirectory(item.path);
  }
}

function goUp(): void {
  if (parentPath.value !== null) {
    loadDirectory(parentPath.value);
  }
}

function confirmSelection(): void {
  if (!selectedPath.value) {
    ElMessage.warning("请先选择一个目录");
    return;
  }
  emit("select", selectedPath.value);
  emit("update:modelValue", false);
}

function cancel(): void {
  emit("update:modelValue", false);
}

watch(
  () => props.modelValue,
  (opened) => {
    if (opened) {
      loadDirectory(props.rootPath || "");
    }
  },
);
</script>

<template>
  <el-dialog :model-value="modelValue" title="选择目录" width="640px" @close="cancel">
    <div class="browser-header">
      <span class="current-path">{{ currentPath || "驱动器列表" }}</span>
      <el-button v-if="parentPath !== null" size="small" @click="goUp">上一级</el-button>
    </div>

    <div class="browser-body" v-loading="loading">
      <div v-if="items.length === 0 && !loading" class="empty-hint">空目录或无权限访问</div>
      <div
        v-for="item in items"
        :key="item.path"
        class="browser-item"
        :class="{ selected: selectedPath === item.path }"
        @click="selectedPath = item.path"
        @dblclick="openDirectory(item)"
      >
        <span class="item-icon">{{ item.is_dir ? "📁" : "📄" }}</span>
        <span class="item-name">{{ item.name }}</span>
        <el-button v-if="item.is_dir" size="small" text @click.stop="openDirectory(item)">进入</el-button>
      </div>
    </div>

    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button type="primary" :disabled="!selectedPath" @click="confirmSelection">选择此目录</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.browser-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.current-path {
  font-family: monospace;
  font-size: 13px;
  color: var(--color-text-secondary);
  word-break: break-all;
}

.browser-body {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  min-height: 280px;
  max-height: 400px;
  overflow-y: auto;
  padding: 4px;
}

.empty-hint {
  text-align: center;
  padding: 48px 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.browser-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.browser-item:hover {
  background: var(--color-bg-muted);
}

.browser-item.selected {
  background: var(--el-color-primary-light-9);
}

.item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.item-name {
  flex: 1;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
