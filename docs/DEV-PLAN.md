# DEV-PLAN.md

> 基于 `Product-Spec.md` 与 `Design-Brief.md` 生成。  
> 默认代码目录：`session-maintenance-system/`。  
> 本文是开发阶段划分、交付边界、关键文件与验收标准的单一计划源。

## 1. 计划目标

在单机 Windows 环境内交付一套可运行的 Session 健康检测与修复后台，覆盖以下 P0 能力：

- 健康检测任务配置、定时/手动检测、失败自动修复、飞书提醒
- 脚本运行实例（ScriptRun）状态追踪、暂停/继续/取消、去重锁
- 脚本库上传、校验、启停、详情查看、运行配置
- Profile 目录注册、锁定/解锁、复检（锁定由脚本运行持有）
- 环境自检、部署配置说明、运行日志检索
- 全局快捷操作（执行环境自检、上传脚本）
- Cookie 扩展采集：采集任务检测（失效→扩展补采→写回→复检）、扩展接入 API、映射管理

## 2. 当前技术栈

以仓库内已锁定依赖为准，不在本计划内主动改栈：

| 层级 | 技术 | 版本来源 |
|---|---|---|
| 后端 | Python | 由运行环境提供，按 3.11 基线执行 |
| 后端框架 | FastAPI | `backend/requirements.txt` 中 `0.138.1` |
| 服务启动 | Uvicorn | `backend/requirements.txt` 中 `0.35.0` |
| 配置管理 | pydantic-settings | `backend/requirements.txt` 中 `2.11.0` |
| ORM | SQLAlchemy | `backend/requirements.txt` 中 `2.0.51` |
| 数据迁移 | Alembic | `backend/requirements.txt` 中 `1.18.0` |
| 数据库驱动 | PyMySQL | `backend/requirements.txt` 中 `1.1.2` |
| 调度器 | APScheduler | `backend/requirements.txt` 中 `3.11.1` |
| 前端框架 | Vue 3 | `frontend/package.json` 中 `3.5.39` |
| 路由 | Vue Router | `frontend/package.json` 中 `4.6.3` |
| 状态管理 | Pinia | `frontend/package.json` 中 `3.0.3` |
| UI 组件 | Element Plus | `frontend/package.json` 中 `2.14.2` |
| 构建工具 | Vite | `frontend/package.json` 中 `8.1.0` |
| 类型系统 | TypeScript | `frontend/package.json` 中 `5.9.2` |

## 3. 开发原则

- 先打通主链路，再做收口优化。
- 先做后端可执行能力，再做前端完整呈现。
- 先建立路径安全、日志、锁机制，再放开脚本执行与人工修复。
- 所有页面实现以 `Product-Spec.md` 为功能真相源，以 `Design-Brief.md` 为视觉与交互真相源。
- 每个 Phase 必须可独立验收，不能写成“铺垫阶段”。

## 4. 依赖顺序

1. 应用骨架、配置、路径安全、通用错误模型
2. 数据模型、迁移、日志基础设施
3. 脚本库与 Profile 目录管理
4. 健康检测任务执行链路（检测 + 修复 + 调度）
5. 脚本运行实例（ScriptRun）与控制能力
6. 环境自检、部署说明、日志检索、前端导航收敛
7. Spec / Design Brief 对齐、联调、验收、发布准备
8. Cookie 采集数据模型与扩展写回能力
9. 扩展接入 API 接收端（任务队列 + 正向映射写库）
10. 采集任务检测与扩展采集闭环（复用健康检测检测逻辑）
11. 采集模块前端页面（采集任务 / 映射管理 / 扩展接入）

## 5. 阶段规划

> 状态标注：✅ 已实现（当前仓库代码已具备） / 🔄 本次变更收口 / ⏳ 待办

### Phase 1：项目骨架与运行时基础 ✅

**目标**

建立前后端可启动骨架、基础路由、全局布局、配置读取与路径安全基线。

**交付物**

- 启动 FastAPI 应用与基础健康检查接口
- 建立 Vue 后台壳层、左侧导航、顶部页面头部与一级页面路由
- 建立 `DEPLOY_ROOT`、`RUNTIME_ROOT` 解析与相对路径校验
- 建立全局设计 tokens 入口，锁定颜色、字体、间距、圆角、状态色

**关键文件**

- `session-maintenance-system/backend/app/main.py`
- `session-maintenance-system/backend/app/core/config.py`
- `session-maintenance-system/backend/app/core/path_utils.py`
- `session-maintenance-system/backend/app/core/errors.py`
- `session-maintenance-system/frontend/src/main.ts`
- `session-maintenance-system/frontend/src/router/index.ts`
- `session-maintenance-system/frontend/src/layouts/AppShell.vue`
- `session-maintenance-system/frontend/src/styles/tokens.css`

**完成标准**

- 后端可启动并返回基础健康检查结果
- 前端可启动并展示完整后台壳层与一级导航
- 非法路径会被拒绝，合法相对路径可解析为绝对路径

### Phase 2：数据模型与持久化基础 ✅

**目标**

建立所有 P0 实体、迁移、数据库访问层与日志基础设施。

**交付物**

- 建立健康检测任务、脚本运行、脚本、Profile、日志、环境自检结果表
- 建立 SQLAlchemy 模型、数据库会话、Alembic 迁移（含新核心表 `health_task`/`script_run`）
- 建立运行日志写入服务
- 建立 legacy cookie 表读取服务

**关键文件**

- `session-maintenance-system/backend/alembic/versions/*.py`
- `session-maintenance-system/backend/app/core/database.py`
- `session-maintenance-system/backend/app/models/health_task.py`
- `session-maintenance-system/backend/app/models/script_run.py`
- `session-maintenance-system/backend/app/models/script_registry.py`
- `session-maintenance-system/backend/app/models/profile_registry.py`
- `session-maintenance-system/backend/app/models/run_log.py`
- `session-maintenance-system/backend/app/models/env_check.py`
- `session-maintenance-system/backend/app/services/run_log_service.py`
- `session-maintenance-system/backend/app/services/legacy_cookie_service.py`

**完成标准**

- 空库可通过 Alembic 初始化出完整业务表
- ORM 与数据库结构一致
- 日志可写入并可读取
- legacy cookie 数据可按业务键查询

### Phase 3：脚本库与 Profile 目录管理 ✅

**目标**

把脚本与浏览器目录变成可管理的标准资源。

**交付物**

- 实现脚本上传、`manifest.json` 校验、落盘、启停、详情查看
- 实现 Profile（目录库）注册、相对路径持久化、绝对路径预览
- 实现 Profile 锁定、解锁、最近验证时间、备注（锁由脚本运行持有）
- 实现脚本页与目录库页的表格、弹窗、状态反馈

**关键文件**

- `session-maintenance-system/backend/app/api/routes/scripts.py`
- `session-maintenance-system/backend/app/api/routes/profiles.py`
- `session-maintenance-system/backend/app/services/script_service.py`
- `session-maintenance-system/backend/app/services/profile_service.py`
- `session-maintenance-system/frontend/src/views/ScriptsView.vue`
- `session-maintenance-system/frontend/src/views/ProfilesView.vue`
- `session-maintenance-system/frontend/src/components/ScriptUploadDialog.vue`
- `session-maintenance-system/frontend/src/components/ScriptDetailDialog.vue`
- `session-maintenance-system/frontend/src/components/ProfileFormDialog.vue`
- `session-maintenance-system/frontend/src/api/scripts.ts`
- `session-maintenance-system/frontend/src/api/profiles.ts`

**完成标准**

- 合法脚本包可落到 `runtime/scripts/uploaded/{script_code}/{version}`
- 非法后缀、路径穿越、缺失 `manifest.json` 会被拒绝
- Profile 仅保存相对路径，页面可显示绝对路径预览

### Phase 4：健康检测任务闭环 ✅

**目标**

让用户可以创建、执行、调度健康检测任务，并在失败时自动修复、飞书提醒。

**交付物**

- 实现健康检测任务 CRUD、启停、克隆、删除、立即检测、执行修复、时间线
- 三 Tab 配置：检测配置 / 高级调度（cron、超时、重试）/ 失败修复（自动修复、脚本、目录、运行模式）
- 实现检测执行：读取 legacy cookie、构造请求、按成功/失败规则判断
- 失败时发送飞书通知；配置自动修复则触发修复脚本；`RISK` 只提醒不建工单
- 实现 APScheduler 定时扫描启用任务，按 cron 触发检测与修复

**关键文件**

- `session-maintenance-system/backend/app/api/routes/health_tasks.py`
- `session-maintenance-system/backend/app/services/health_task_service.py`
- `session-maintenance-system/backend/app/services/scheduler_service.py`
- `session-maintenance-system/backend/app/services/notification_service.py`
- `session-maintenance-system/frontend/src/views/HealthTasksView.vue`
- `session-maintenance-system/frontend/src/api/healthTasks.ts`

**完成标准**

- 健康检测任务可创建、编辑、执行、启停、克隆、删除
- 检测通过写入 `PASS`，失败写入 `FAIL` 并飞书通知
- 启用自动修复的任务失败后自动触发修复脚本
- `RISK` 时状态回到 `PENDING`，只发送提醒、不生成工单

### Phase 5：脚本运行实例（ScriptRun）✅

**目标**

追踪每次脚本执行生命周期，提供状态、产物、日志与控制能力。

**交付物**

- 实现 ScriptRun 实例列表、详情、实时日志、result.json
- 实现 `PENDING/RUNNING/PAUSED/CANCELING/CANCELED/SUCCESS/FAIL/RISK` 状态机
- 实现暂停/继续/取消（写 `control.json`，取消杀进程树）
- 实现目录去重锁：同脚本+目录进行中实例存在时阻止重复执行

**关键文件**

- `session-maintenance-system/backend/app/api/routes/script_runs.py`
- `session-maintenance-system/backend/app/services/script_run_service.py`
- `session-maintenance-system/backend/app/services/local_windows_executor.py`
- `session-maintenance-system/backend/app/services/process_runner.py`
- `session-maintenance-system/frontend/src/views/ScriptRunsView.vue`
- `session-maintenance-system/frontend/src/api/scriptRuns.ts`

**完成标准**

- 脚本运行实例可查看状态、产物、日志
- 暂停/继续/取消真实作用于运行中的进程
- 目录锁与去重阻止并发执行

### Phase 6：旧模块清理与发布收口 🔄

**目标**

删除已废弃的旧架构模块，收敛导航，恢复可构建环境并发布。

**交付物**

- 删除旧模块前后端代码：总览 Dashboard、维护任务（SessionTask）、旧健康检测（HealthCheckConfig）、人工修复工单（ManualRepairTicket）
- 收敛导航为 7 项，删除总览/人工修复入口，进系统默认落健康检测任务页
- 收敛全局快捷操作为：执行环境自检、上传脚本
- 清理 Profile 的"绑定任务"字段（旧维护任务已废弃）
- 修复 `health_task_service` RISK 分支：由 TODO 改为飞书提醒
- 重装 `frontend/node_modules` 恢复前端构建（当前迁移后 bin shim 指向旧盘路径）
- 删除旧模块相关测试，重跑后端测试与前端构建
- 更新 README、启动说明，完成发布验证

**关键文件**

- 删除：`backend/app/api/routes/{dashboard,session_tasks,health_checks,repairs}.py`
- 删除：`backend/app/services/{dashboard_service,session_task_service,health_check_service,repair_service}.py`
- 删除：`backend/app/models/{session_task,health_check,repair_ticket}.py`
- 删除：`frontend/src/views/{DashboardView,SessionTasksView,HealthChecksView,RepairsView}.vue`
- 删除：`frontend/src/components/{TaskFormDialog,TaskDetailDialog,HealthCheckFormDialog,RepairGuideDialog}.vue`
- 删除：`frontend/src/api/{dashboard,sessionTasks,healthChecks,repairs}.ts`
- 修改：`backend/app/main.py`、`backend/app/models/__init__.py`、`backend/app/services/__init__.py`、`backend/app/services/profile_service.py`
- 修改：`frontend/src/router/index.ts`、`frontend/src/layouts/AppShell.vue`、`frontend/src/components/QuickActionBar.vue`
- 修改：`session-maintenance-system/README.md`

**完成标准**

- `Product-Spec.md` 新架构全部 P0 页面、动作、字段、状态已覆盖
- 后端 `compileall` 通过，旧模块测试清理后测试套件通过
- 前端 `npm run build` 通过，导航与快捷操作符合新 Spec
- 主链路 `定时检测 -> 失败 -> 自动修复 -> 飞书提醒 -> 状态回写` 跑通

### Phase 7：Cookie 采集数据模型与扩展写回能力 ✅

**目标**

建立采集任务、映射、任务队列三张表，并让 legacy cookie 服务具备先查后改的写回能力，作为采集模块的数据地基。

**交付物**

- 新增 CookieSyncTask / CookieSyncMapping / CookieSyncJob 模型与 Alembic 迁移
- 扩展 `legacy_cookie_service.py`：按 `(channel, shop_name, mobile_phone, dns)` 先查后改写回旧表（填 `cookie` JSON + `str_cookie` 拼接串）
- `config.py` 新增 `COOKIE_SYNC_API_KEY` 配置（.env / .env.example）

**关键文件**

- `backend/alembic/versions/*.py`（新增三表迁移）
- `backend/app/models/cookie_sync_task.py`
- `backend/app/models/cookie_sync_mapping.py`
- `backend/app/models/cookie_sync_job.py`
- `backend/app/models/__init__.py`（注册新模型）
- `backend/app/services/legacy_cookie_service.py`（写回方法）
- `backend/app/core/config.py`、`.env.example`、`.env`（`COOKIE_SYNC_API_KEY`）

**完成标准**

- 空库迁移可建出三张新表，`cookie_sync_mapping` 以 `(worker_id, domain)` 唯一
- legacy 写回：已有记录更新、无记录插入，`str_cookie` 拼接正确
- 后端测试通过（含写回单测）

### Phase 8：扩展接入 API 接收端 ✅

**目标**

实现 Chrome 扩展契约五条接口，`X-API-Key` 鉴权，正向映射写库，任务队列定向出队，让同事电脑上的扩展能连上平台。

**交付物**

- 新增 cookie_sync 路由：`GET /api/ping`（无鉴权）、`POST /api/request`、`GET /api/tasks?worker_id=`、`POST /api/tasks/{id}/report`、`POST /api/cookies`
- 新增 `X-API-Key` 鉴权依赖（非 ping 接口校验 `COOKIE_SYNC_API_KEY`；key 留空关闭鉴权，仅限本地联调，生产必填）
- 新增 `cookie_sync_service`：任务入队/定向匹配、上报按映射正向写库、无映射丢弃记 WARN、上报 worker 与定向不一致以定向为准
- 注册路由到 `main.py`

**关键文件**

- `backend/app/api/routes/cookie_sync.py`
- `backend/app/api/deps.py`（`X-API-Key` 校验依赖）
- `backend/app/services/cookie_sync_service.py`
- `backend/app/main.py`

**完成标准**

- 用 TestClient 走通 `ping → request → tasks?worker_id → report`，库中按映射写入正确（cookie + str_cookie）
- 无/错 `X-API-Key` 返回 401；无映射上报丢弃并记 WARN 日志

### Phase 9：采集任务检测与扩展采集闭环 ✅

**目标**

实现采集任务 CRUD 与"检测失效→扩展采集→写回→复检"闭环，复用健康检测的检测执行逻辑，飞书通知收尾。

**交付物**

- 采集任务 CRUD / 启停 / 克隆 / 删除 / 立即检测 路由与 service
- 复用健康检测检测逻辑：读 legacy cookie → 构造请求 → 成功/失败规则判定
- 失效时按映射反向查 `(worker_id, domain)` → 入队采集任务（定向派给该 worker）→ 等待上报（`sync_wait_timeout_seconds` 默认 180）→ 写回旧表 → 复检
- 复检通过 `PASS`；无映射 / 等待超时 / 复检仍失败 → `FAIL` + 飞书
- APScheduler 扩展扫描启用采集任务，按 cron 触发检测

**关键文件**

- `backend/app/api/routes/cookie_sync_tasks.py`
- `backend/app/services/cookie_sync_task_service.py`
- `backend/app/schemas/cookie_sync_task.py`
- `backend/app/services/scheduler_service.py`（采集任务扫描）
- `backend/app/services/notification_service.py`（复用飞书）

**完成标准**

- 建采集任务 → 检测失效 → 进入 `SYNCING` → 模拟扩展上报 → 写回 → 复检 `PASS`
- 无映射 / 超时 → `FAIL` + 飞书；后端测试与编译通过

### Phase 10：采集模块前端页面 ✅

**目标**

导航加入口，实现采集任务、映射管理、扩展接入三个页面，与后端联通。

**交付物**

- 导航新增「Cookie 采集任务」入口（位于健康检测任务之后）
- 采集任务列表 / 编辑弹窗（检测配置 / 调度 / 同步设置三 Tab）、启停、克隆、删除、立即检测
- 映射管理页：`worker_id / domain / channel / shop_name / mobile_phone / dns` CRUD
- 扩展接入信息页：后端地址、`COOKIE_SYNC_API_KEY`、扩展安装指引
- API client：`cookieSyncTasks.ts` / `cookieSyncMappings.ts`
- 将扩展包复制纳入仓库 `extension/` 便于分发

**关键文件**

- `frontend/src/router/index.ts`、`frontend/src/layouts/AppShell.vue`
- `frontend/src/views/CookieSyncTasksView.vue`
- `frontend/src/views/CookieSyncMappingView.vue`
- `frontend/src/views/CookieSyncAccessView.vue`
- `frontend/src/api/cookieSyncTasks.ts`、`frontend/src/api/cookieSyncMappings.ts`
- `extension/`（从 `D:\公司小疑问\chrome扩展` 复制）

**完成标准**

- 采集任务与映射可在页面增删改查，立即检测/触发采集与后端联通
- 扩展接入信息页展示地址、密钥、安装步骤；前端 `npm run build` 通过

## 6. 数据库表与归属阶段

| 表 / 实体 | 归属阶段 | 说明 |
|---|---|---|
| `health_task` | Phase 2 / 4 | 健康检测任务：检测配置、调度、失败修复、状态 |
| `script_run` | Phase 2 / 5 | 脚本运行实例：状态机、PID、产物、控制 |
| `script_registry` | Phase 2 / 3 | 脚本元信息、版本、启停、运行配置 |
| `profile_registry` | Phase 2 / 3 | Profile 目录路径、锁状态（`is_locked`/`lock_owner`/`lock_run_id`） |
| `task_run_log` | Phase 2 / 7 | 健康检测、修复脚本运行日志 |
| `env_check_result` | Phase 2 / 7 | 最近一次环境自检结果 |
| `cookie_sync_task` | Phase 7 / 9 | 采集任务：检测配置、调度、同步超时、状态 |
| `cookie_sync_mapping` | Phase 7 / 8 | 采集映射：`(worker_id, domain) → channel/shop_name/mobile_phone/dns` |
| `cookie_sync_job` | Phase 7 / 8 | 扩展采集任务队列：`task_id/worker_id/domains/status` |
| `ods_cookie_playwright` | 外部依赖 | legacy cookie 数据来源；健康检测只读，扩展采集写回（Phase 7 起具备写回能力） |
| `session_maintenance_task` | 已废弃 | 旧维护任务表，保留数据不再读写 |
| `health_check_config` | 已废弃 | 旧健康检测表，保留数据不再读写 |
| `manual_repair_ticket` | 已废弃 | 旧人工修复工单表，保留数据不再读写 |

## 7. 每阶段验证要求

每个 Phase 完成时都必须执行以下验证，缺一项都不算完成：

1. 代码审查：确认行为、边界条件、错误处理和回归风险。
2. 测试验证：补齐与本阶段风险相称的后端测试或接口测试。
3. 编译验证：后端至少通过导入/编译检查，前端至少通过构建检查。
4. 功能验证：对照本 Phase 完成标准做一次真实操作验证。

## 8. 建议执行顺序

如果按全新项目推进，严格按 Phase 1 到 Phase 10 执行。  
如果基于当前仓库继续推进，Phase 1-5 已实现，旧模块清理（Phase 6 主体）已完成。后续：

1. **Phase 6 收口**：确认导航/快捷操作/README/启动说明/回归测试已收敛到 7 项导航的新架构（当前代码已基本达成，做最终回归）。
2. **Phase 7-10（Cookie 扩展采集模块）**：
   - Phase 7 采集数据模型与扩展写回能力
   - Phase 8 扩展接入 API 接收端
   - Phase 9 采集任务检测与扩展采集闭环
   - Phase 10 采集模块前端页面
3. 全部通过后做完整联调与发布准备。

> 说明：扩展本体（Chrome 扩展）已在 `D:\公司小疑问\chrome扩展` 联调验证过，平台侧只需实现接收端 API，扩展代码不改（Phase 8 以现有 `background.js` 契约为准；Phase 10 将扩展包纳入仓库便于分发）。
