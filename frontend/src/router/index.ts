import { createRouter, createWebHistory } from "vue-router";

import DashboardView from "@/views/DashboardView.vue";
import DeployView from "@/views/DeployView.vue";
import EnvironmentView from "@/views/EnvironmentView.vue";
import HealthChecksView from "@/views/HealthChecksView.vue";
import HealthTasksView from "@/views/HealthTasksView.vue";
import LogsView from "@/views/LogsView.vue";
import PlaceholderView from "@/views/PlaceholderView.vue";
import ProfilesView from "@/views/ProfilesView.vue";
import RepairsView from "@/views/RepairsView.vue";
import ScriptRunsView from "@/views/ScriptRunsView.vue";
import ScriptsView from "@/views/ScriptsView.vue";
import SessionTasksView from "@/views/SessionTasksView.vue";

const routes = [
  { path: "/", redirect: "/dashboard" },
  {
    path: "/dashboard",
    component: DashboardView,
    meta: {
      title: "总览",
      description: "查看系统当前状态、最近日志、最近健康检测，并直接触发全局高频动作。",
    },
  },
  {
    path: "/tasks",
    component: SessionTasksView,
    meta: {
      title: "维护任务",
      description: "创建维护任务、查看绑定信息、手动执行脚本，并在风险场景下直达人工修复。",
    },
  },
  {
    path: "/checks",
    component: HealthChecksView,
    meta: {
      title: "健康检测（旧）",
      description: "旧版健康检测页面，即将迁移到健康检测任务。",
    },
  },
  {
    path: "/health-tasks",
    component: HealthTasksView,
    meta: {
      title: "健康检测任务",
      description: "配置旧 cookie 检测规则、高级调度和失败后自动修复。检测失败时自动执行维护脚本并写入新 cookie。",
    },
  },
  {
    path: "/profiles",
    component: ProfilesView,
    meta: {
      title: "Profile 目录",
      description: "登记、锁定、解锁和复检浏览器 Profile，并在需要时直接打开修复浏览器。",
    },
  },
  {
    path: "/scripts",
    component: ScriptsView,
    meta: {
      title: "脚本库",
      description: "上传脚本包、查看脚本元信息，并切换启停状态。",
    },
  },
  {
    path: "/script-runs",
    component: ScriptRunsView,
    meta: {
      title: "脚本运行",
      description: "查看所有脚本执行实例，支持暂停、继续和取消正在执行的脚本。",
    },
  },
  {
    path: "/repairs",
    component: RepairsView,
    meta: {
      title: "人工修复",
      description: "处理 RISK 工单，在部署机打开修复浏览器，并在完成人工验证后发起复检。",
    },
  },
  {
    path: "/environment",
    component: EnvironmentView,
    meta: {
      title: "环境自检",
      description: "执行 Windows 节点环境自检，确认目录、数据库和桌面会话是否可用。",
    },
  },
  {
    path: "/deploy",
    component: DeployView,
    meta: {
      title: "部署配置",
      description: "查看部署根目录、运行目录、关键子目录和启动命令。",
    },
  },
  {
    path: "/logs",
    component: LogsView,
    meta: {
      title: "运行日志",
      description: "按类型、状态和关键字筛选运行记录，快速定位最近一次失败。",
    },
  },
  {
    path: "/:pathMatch(.*)*",
    component: PlaceholderView,
    meta: {
      title: "未找到页面",
      description: "当前路由不存在，请从左侧导航返回已接入页面。",
    },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
