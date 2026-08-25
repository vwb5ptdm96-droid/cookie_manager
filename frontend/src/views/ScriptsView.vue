<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { fetchProfiles, type ProfileItem } from "@/api/profiles";
import { cloneScript, deleteScript, fetchCdpPortStatus, fetchScriptFiles, fetchScripts, toggleScript, updateScriptMainFile, updateScriptProfile, updateScriptRunConfig, uploadScript, type CdpPortStatus, type ScriptItem, type ScriptUploadPayload } from "@/api/scripts";
import ScriptDetailDialog from "@/components/ScriptDetailDialog.vue";
import ScriptUploadDialog from "@/components/ScriptUploadDialog.vue";

const route = useRoute();
const router = useRouter();

const scripts = ref<ScriptItem[]>([]);
const profiles = ref<ProfileItem[]>([]);
const loading = ref(false);
const uploading = ref(false);
const dialogVisible = ref(false);
const detailVisible = ref(false);
const currentScript = ref<ScriptItem | null>(null);
const scriptFilesMap = ref<Record<string, string[]>>({});
const loadingFiles = ref<Record<string, boolean>>({});

const enabledCount = computed(() => scripts.value.filter((item) => item.enabled).length);

async function loadData(): Promise<void> {
  loading.value = true;
  try {
    const [scriptData, profileData] = await Promise.all([fetchScripts(), fetchProfiles()]);
    scripts.value = scriptData.items;
    profiles.value = profileData.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载数据失败");
  } finally {
    loading.value = false;
  }
}

async function handleProfileChange(script: ScriptItem, profileKey: string | null): Promise<void> {
  try {
    await updateScriptProfile(script.script_code, profileKey);
    ElMessage.success("关联目录已更新");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "更新失败");
  }
}

async function handleUpload(payload: ScriptUploadPayload): Promise<void> {
  uploading.value = true;
  try {
    await uploadScript(payload);
    dialogVisible.value = false;
    ElMessage.success("脚本已上传");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function handleRunModeChange(script: ScriptItem, value: string | null): Promise<void> {
  try {
    const result = await updateScriptRunConfig(script.script_code, { default_run_mode: value || null });
    script.default_run_mode = result.default_run_mode;
    ElMessage.success("运行模式已更新");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "更新运行模式失败");
  }
}

async function handleCdpPortChange(script: ScriptItem, value: number | null): Promise<void> {
  try {
    const result = await updateScriptRunConfig(script.script_code, { default_cdp_port: value || null });
    script.default_cdp_port = result.default_cdp_port;
    ElMessage.success("CDP 端口已更新");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "更新 CDP 端口失败");
  }
}

const portStatusVisible = ref(false);
const portStatusList = ref<CdpPortStatus[]>([]);
const portStatusLoading = ref(false);

async function openPortStatus(): Promise<void> {
  portStatusVisible.value = true;
  portStatusLoading.value = true;
  try {
    portStatusList.value = await fetchCdpPortStatus();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "获取端口状态失败");
  } finally {
    portStatusLoading.value = false;
  }
}

async function handleToggle(script: ScriptItem): Promise<void> {
  try {
    await toggleScript(script.script_code, !script.enabled);
    ElMessage.success(script.enabled ? "脚本已停用" : "脚本已启用");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "切换状态失败");
  }
}

async function loadScriptFiles(scriptCode: string): Promise<void> {
  if (scriptFilesMap.value[scriptCode] || loadingFiles.value[scriptCode]) return;
  loadingFiles.value[scriptCode] = true;
  try {
    const files = await fetchScriptFiles(scriptCode);
    scriptFilesMap.value[scriptCode] = files;
  } catch (error) {
    ElMessage.error("获取脚本文件列表失败");
  } finally {
    loadingFiles.value[scriptCode] = false;
  }
}

async function handleMainFileChange(script: ScriptItem, mainFile: string): Promise<void> {
  try {
    await updateScriptMainFile(script.script_code, mainFile);
    script.main_file = mainFile;
    ElMessage.success("入口文件已更新");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "更新入口文件失败");
  }
}

function openDetail(script: ScriptItem): void {
  currentScript.value = script;
  detailVisible.value = true;
}

function openEdit(script: ScriptItem): void {
  currentScript.value = script;
  detailVisible.value = true;
}

async function handleClone(script: ScriptItem): Promise<void> {
  try {
    await cloneScript(script.script_code);
    ElMessage.success("脚本已复制");
    await loadData();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "复制失败");
  }
}

function handleDetailSaved(): void {
  void loadData();
}

async function handleDelete(script: ScriptItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除脚本「${script.script_name}」？删除后文件和记录将不可恢复。`, "确认删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await deleteScript(script.script_code);
    ElMessage.success("脚本已删除");
    await loadData();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error instanceof Error ? error.message : "删除失败");
    }
  }
}

async function clearUploadQuery(): Promise<void> {
  const query = { ...route.query };
  delete query.upload;
  await router.replace({ path: route.path, query });
}

watch(
  () => route.query.upload,
  async (value) => {
    if (value === "1") {
      dialogVisible.value = true;
      await clearUploadQuery();
    }
  },
  { immediate: true },
);

onMounted(loadData);
</script>

<template>
  <section class="page-grid">
    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">脚本总数</span>
        <strong class="summary-value">{{ scripts.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">启用中</span>
        <strong class="summary-value">{{ enabledCount }}</strong>
      </article>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>脚本库</h2>
          <p>上传 CDP Python 脚本、关联 Profile 目录并执行。脚本编码和版本由系统自动管理。</p>
        </div>
        <el-button @click="openPortStatus">端口状态</el-button>
        <el-button type="primary" @click="dialogVisible = true">上传脚本</el-button>
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="scripts" row-key="script_code" empty-text="暂无脚本。准备一个合法的 .py 脚本文件，点击「上传脚本」添加到脚本库。">
          <el-table-column prop="script_name" label="脚本名称" min-width="160" />
          <el-table-column prop="script_type" label="类型" min-width="100" />
          <el-table-column prop="platform" label="平台" min-width="100" />
          <el-table-column label="选择目录" min-width="200">
            <template #default="{ row }">
              <el-select
                :model-value="row.profile_key"
                placeholder="选择 Profile 目录"
                size="small"
                clearable
                @change="(val: string | null) => handleProfileChange(row, val)"
              >
                <el-option
                  v-for="profile in profiles"
                  :key="profile.profile_key"
                  :label="profile.profile_key"
                  :value="profile.profile_key"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="入口文件" min-width="200">
            <template #default="{ row }">
              <el-select
                :model-value="row.main_file"
                size="small"
                placeholder="选择入口文件"
                :loading="!!loadingFiles[row.script_code]"
                @visible-change="(visible: boolean) => visible && loadScriptFiles(row.script_code)"
                @change="(val: string) => handleMainFileChange(row, val)"
              >
                <el-option
                  v-for="f in scriptFilesMap[row.script_code] || []"
                  :key="f"
                  :label="f"
                  :value="f"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="运行模式" min-width="120">
            <template #default="{ row }">
              <el-select
                :model-value="row.default_run_mode"
                size="small"
                @change="handleRunModeChange(row, $event)"
              >
                <el-option label="无头模式" value="HEADLESS" />
                <el-option label="有头模式" value="HEADED" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="CDP 端口" min-width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.default_cdp_port"
                :min="1024"
                :max="65535"
                size="small"
                controls-position="right"
                placeholder="9222"
                @change="handleCdpPortChange(row, $event)"
              />
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="100">
            <template #default="{ row }">
              <span class="cell-desc">{{ row.description || "—" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280">
            <template #default="{ row }">
              <div class="actions">
                <el-button size="small" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" @click="handleToggle(row)">{{ row.enabled ? "停用" : "启用" }}</el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => cmd === 'clone' ? handleClone(row) : handleDelete(row)">
                  <el-button size="small">
                    更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="clone">复制</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <ScriptUploadDialog v-model="dialogVisible" :submitting="uploading" @submit="handleUpload" />
    <ScriptDetailDialog v-model="detailVisible" :script="currentScript" @saved="handleDetailSaved" />

    <!-- CDP 端口状态对话框 -->
    <el-dialog v-model="portStatusVisible" title="CDP 端口状态" width="600px" top="15vh">
      <el-table v-loading="portStatusLoading" :data="portStatusList" empty-text="没有脚本配置了 CDP 端口">
        <el-table-column prop="port" label="端口" width="100" />
        <el-table-column prop="script_name" label="所属脚本" min-width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.in_use ? 'success' : 'info'" effect="plain">
              {{ row.in_use ? "浏览器已打开" : "空闲" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <div class="dialog-actions">
          <el-button :loading="portStatusLoading" @click="openPortStatus">刷新</el-button>
          <el-button type="primary" @click="portStatusVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.page-grid,
.summary-grid {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-card,
.panel {
  padding: 18px;
  border: 1px solid #dfe5ee;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
}

.summary-label {
  display: block;
  color: #667085;
  font-size: 13px;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 28px;
  line-height: 1.1;
  color: #172033;
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
  color: #667085;
}

.actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.path-cell {
  display: grid;
  gap: 4px;
}

.path-cell .el-select {
  width: 100%;
}

.cell-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.path-cell span {
  color: #667085;
  font-size: 12px;
  word-break: break-all;
}

/* ── el-select 样式覆盖 ── */
:deep(.el-select .el-select__wrapper) {
  background: #f8fafc;
  border: 1px solid #dfe5ee;
  border-radius: 8px;
  box-shadow: none;
  min-height: 30px;
  padding: 0 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
:deep(.el-select .el-select__wrapper:hover) {
  border-color: #2563eb;
}
:deep(.el-select .el-select__wrapper.is-focused) {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
:deep(.el-select .el-select__input) {
  color: #172033;
}
:deep(.el-select .el-select__placeholder) {
  color: #667085;
}
:deep(.el-select .el-select__selection span) {
  color: #172033;
  font-size: 13px;
}

/* 下拉面板 */
:deep(.el-select__popper.el-popper) {
  border: 1px solid #dfe5ee;
  border-radius: 12px;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
  background: #ffffff;
}
:deep(.el-select__popper .el-popper__arrow::before) {
  border-color: #dfe5ee;
}
:deep(.el-select__popper .el-select-dropdown__item) {
  color: #172033;
  font-size: 13px;
  border-radius: 6px;
  margin: 2px 4px;
  padding: 0 10px;
  height: 32px;
  line-height: 32px;
}
:deep(.el-select__popper .el-select-dropdown__item.hover) {
  background: #f4f7fb;
}
:deep(.el-select__popper .el-select-dropdown__item.selected) {
  color: #2563eb;
  font-weight: 600;
  background: #f4f7fb;
}

/* 清除按钮和箭头 */
:deep(.el-select .el-select__clear) {
  color: #667085;
}
:deep(.el-select .el-select__clear:hover) {
  color: #172033;
}
:deep(.el-select .el-select__suffix .el-icon) {
  color: #667085;
}

/* 加载状态 */
:deep(.el-select.is-loading .el-select__wrapper) {
  background: #f4f7fb;
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
