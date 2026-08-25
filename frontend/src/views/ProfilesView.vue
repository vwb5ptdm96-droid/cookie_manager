<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { createProfile, deleteProfile, fetchProfiles, updateProfile, type ProfileItem, type ProfileUpsertPayload } from "@/api/profiles";
import { fetchScripts, updateScriptProfile, type ScriptItem } from "@/api/scripts";
import ProfileFormDialog from "@/components/ProfileFormDialog.vue";

const profiles = ref<ProfileItem[]>([]);
const scripts = ref<ScriptItem[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const submitting = ref(false);
const editingProfile = ref<ProfileItem | null>(null);

function findBoundScripts(profile: ProfileItem): ScriptItem[] {
  return scripts.value.filter((item) => item.profile_key === profile.profile_key);
}

async function loadProfiles(): Promise<void> {
  loading.value = true;
  try {
    const [profileData, scriptData] = await Promise.all([fetchProfiles(), fetchScripts()]);
    profiles.value = profileData.items;
    scripts.value = scriptData.items;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载 Profile 失败");
  } finally {
    loading.value = false;
  }
}

function handleEdit(profile: ProfileItem): void {
  editingProfile.value = profile;
  dialogVisible.value = true;
}

async function handleDelete(profile: ProfileItem): Promise<void> {
  try {
    await deleteProfile(profile.profile_key);
    ElMessage.success("Profile 已删除");
    await loadProfiles();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除 Profile 失败");
  }
}

async function handleSave(payload: ProfileUpsertPayload, scriptCodes: string[]): Promise<void> {
  submitting.value = true;
  try {
    const savedKey = editingProfile.value?.profile_key ?? null;
    if (editingProfile.value) {
      await updateProfile(savedKey!, payload);
    } else {
      await createProfile(payload);
    }

    const boundKey = payload.profile_key;
    const prevBound = scripts.value
      .filter((s) => s.profile_key === (savedKey !== boundKey ? savedKey : boundKey))
      .map((s) => s.script_code);

    for (const code of prevBound) {
      if (!scriptCodes.includes(code)) {
        await updateScriptProfile(code, null);
      }
    }
    for (const code of scriptCodes) {
      if (!prevBound.includes(code)) {
        await updateScriptProfile(code, boundKey);
      }
    }

    dialogVisible.value = false;
    editingProfile.value = null;
    ElMessage.success("Profile 已保存");
    await loadProfiles();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存 Profile 失败");
  } finally {
    submitting.value = false;
  }
}

onMounted(loadProfiles);
</script>

<template>
  <section class="page-grid">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Profile 目录</h2>
          <p>登记浏览器用户数据目录，支持相对路径（runtime/profiles/…）或绝对路径。目录为登记的资产，内容由脚本库操作维护。</p>
        </div>
        <el-button type="primary" @click="dialogVisible = true">登记 Profile</el-button>
      </div>

      <div class="table-shell">
        <el-table v-loading="loading" :data="profiles" row-key="profile_key" empty-text="暂无登记 Profile。点击「登记 Profile」添加一条记录。">
          <el-table-column prop="profile_key" label="Profile Key" min-width="160" />
          <el-table-column label="绑定脚本" min-width="200">
            <template #default="{ row }">
              <div class="bound-tasks">
                <template v-if="findBoundScripts(row).length > 0">
                  <div v-for="script in findBoundScripts(row)" :key="script.script_code" class="bound-task-item">
                    <el-tag size="small" :type="script.enabled ? '' : 'info'">
                      {{ script.script_name }}
                    </el-tag>
                  </div>
                </template>
                <span v-else class="empty-hint">未绑定脚本</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="路径预览" min-width="300">
            <template #default="{ row }">
              <div class="path-cell">
                <code>{{ row.relative_path }}</code>
                <span>{{ row.absolute_path }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="handleEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <ProfileFormDialog v-model="dialogVisible" :scripts="scripts" :submitting="submitting" :profile="editingProfile" @submit="handleSave" />
  </section>
</template>

<style scoped>
.page-grid {
  display: grid;
  gap: 16px;
}

.panel {
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
.panel-header p {
  margin: 0;
}

.panel-header p {
  margin-top: 6px;
  color: var(--color-text-secondary);
}

.path-cell {
  display: grid;
  gap: 4px;
}

.path-cell span {
  color: var(--color-text-secondary);
  font-size: 12px;
  word-break: break-all;
}

.bound-tasks {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bound-task-item {
  display: inline-flex;
}

.empty-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
}
</style>
