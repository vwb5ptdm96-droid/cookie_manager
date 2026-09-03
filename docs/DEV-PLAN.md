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
- Cookie 一键上报：独立扩展以悬浮球抓取当前页 cookie 与请求头（chrome.debugger），手动填业务定位字段写回旧表
- 生产服务化托管与运维加固：计划任务入口、健康探针、日志轮转、运维文档
- 自动排障闭环：修复失败/异常/风控自动唤起 Claude Code 连 CDP 排障，回写 SOLVED/NEED_HUMAN

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
12. 手动 Cookie 上报扩展（`/api/cookies/manual` 端点 + 独立"Cookie 一键上报"扩展）
13. Headers 捕获（chrome.debugger / CDP，捕获当前域名 API 完整请求头）

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

> **现状更新（2026-09-03 回写）**：本阶段主体已于 8/25 架构收敛时完成（导航收敛 7 项、旧模块删除、README/启动说明对齐）。但 2026-09-02 提交（`e929250`/`ec32798` 等）将同名旧模块代码（`session_tasks`/`health_checks`/`repairs`/`dashboard` 后端路由 + 前端孤儿 view）意外回潮——后端已注册进 `main.py` 并自带全套测试，但前端 router/导航无任何引用、也无业务模块依赖它们。判定为废弃残留（Spec OUT-007/008），**列为待清理项**：不回滚、不在此仓库删除（主工作区为内部机 `D:\session-maintenance-system`），由内部机统一清理。本阶段维持 🔄（收口未最终达成）。

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

- 采集任务 CRUD / 启停 / 克隆 / 删除 / 立即检测 / 手动执行扩展采集 路由与 service
- 复用健康检测检测逻辑：读 legacy cookie → 构造请求 → 成功/失败规则判定
- 失效时按映射反向查 `(worker_id, domain)` → 入队采集任务（定向派给该 worker）→ 等待上报（`sync_wait_timeout_seconds` 默认 180）→ 写回旧表 → 复检
- 手动执行扩展采集（`POST /{code}/repair`）：不经过检测直接反查映射下发采集任务进入 `SYNCING`，复用同一闭环；无映射报错，已在 `SYNCING` 跳过
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
- 手动执行扩展采集 → 直接 `SYNCING`；无映射报错 `NO_MAPPING`；后端测试与编译通过
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

### Phase 11：部署配置可移植化 ✅

**目标**

让部署链路完全由 `.env` 驱动，部署机无 E 盘、默认端口被占时改 `.env` 即可启动，清理硬编码端口。

**交付物**

- 前端开发代理按根目录 `.env` 的 `APP_PORT` 解析目标，不再写死 `8081`
- 扩展接入后端地址展示改为按当前页面 `origin` 动态取，不再写死 `:8081/api`
- `.env.example` / README 补部署说明：路径项不配走自动检测、`APP_PORT` 换空闲端口、`CHROME_PATH` 指定调试 Chrome

**关键文件**

- `frontend/vite.config.ts`
- `frontend/src/views/CookieSyncTasksView.vue`
- `.env.example`、`README.md`

**完成标准**

- 部署机 `.env` 配置不同端口/路径后，点 `start_backend.bat` 可正常拉起后端与前端（`dist` 同端口托管）
- 前端无硬编码后端端口，扩展接入地址按当前 origin 动态展示

### Phase 12：目录库 CDP 调试功能 ✅

**目标**

目录库每目录存默认调试端口，可一键拉起/关闭带该目录的可见 Chrome（CDP 端口供外部脚本连接调试）。

**交付物**

- `profile_registry` 新增 `debug_port` 列 + Alembic 迁移
- `config.py` 新增 `CHROME_PATH`（未配置自动探测常见安装路径）
- 新增调试端点：`POST /api/profiles/{key}/debug/open`（拉起 headed Chrome：`--user-data-dir` + `--remote-debugging-port`，等待 CDP 就绪返回调试地址）、`POST /api/profiles/{key}/debug/close`（清理该目录/端口 Chrome）
- 目录锁定（`is_locked`）时打开调试被拒（后端 `DIRECTORY_LOCKED`）
- 目录库页面：调试端口列、「打开调试」「关闭调试」按钮（锁定时置灰）；Profile 弹窗新增调试端口字段

**关键文件**

- `backend/app/models/profile_registry.py`、`backend/alembic/versions/*.py`
- `backend/app/core/config.py`、`backend/app/services/chrome_utils.py`
- `backend/app/services/profile_service.py`、`backend/app/api/routes/profiles.py`
- `backend/app/schemas/profile_registry.py`
- `frontend/src/views/ProfilesView.vue`、`frontend/src/components/ProfileFormDialog.vue`、`frontend/src/api/profiles.ts`

**完成标准**

- 目录可设置调试端口；未锁定目录点「打开调试」拉起带该目录的可见 Chrome 并返回调试地址
- 锁定目录点「打开调试」前端置灰、后端返回 `DIRECTORY_LOCKED`
- 「关闭调试」清理对应 Chrome；后端测试与前端 `npm run build` 通过

### Phase 13：手动 Cookie 上报扩展 ✅

**目标**

实现"Cookie 一键上报"独立扩展与手动上报端点：用户在自己浏览器打开已登录页面，一键抓取当前页面 cookie，手动填写 `channel/shop_name/mobile_phone/dns`，直接写回旧表。不经映射表、无采集者概念、不挂平台前端。

**交付物**

- 后端新增 `POST /api/cookies/manual` 端点：body `{channel, shop_name, mobile_phone, dns, cookies, collected_at}` → `{ok, stored, is_new}`；复用 `legacy_cookie_service.upsert_by_lookup` 按四字段先查后改（存在更新、不存在插入，填 `cookie` JSON + `str_cookie` 拼接串）；沿用 `X-API-Key` 鉴权（非 ping 接口）
- 新增 schema `CookieSyncManualUpload`（channel/dns 必填非空、shop_name/mobile_phone 可空、cookies 非空）
- 新增独立 MV3 扩展 `extension/cookie-quick-upload/`（命名"Cookie 一键上报"，与 `extension/` 的"Cookie 同步助手"并存），主入口为页面内可移动悬浮球：
  - background service worker：处理「读取当前标签页 cookie」「上报」「测试连接」三类消息（content script 的 fetch 受页面 CORS 限制，网络请求全部经 background 转发）
  - content script（`content.js`）：向 http/https 页面注入可拖动悬浮球，点击展开上报面板（DOM 渲染）；面板展示 cookie 数（脱敏名称列表）、四字段表单、测试连接/上报/刷新重抓按钮
  - 抓取为空时提供「刷新页面并重新获取」：`chrome.tabs.reload` 当前标签页后延迟重新抓取
  - 「测试连接」按钮经 background 调 `GET /api/ping`，展示后端联通结果（可达/不可达及原因）
  - options 页配置 `backendUrl` + `apiKey`（不依赖平台前端）

**关键文件**

- `backend/app/api/routes/cookie_sync.py`（新增 manual 端点）
- `backend/app/schemas/cookie_sync.py`（新增 `CookieSyncManualUpload`）
- `backend/app/services/cookie_sync_service.py`（新增手动上报处理，复用 legacy 写回）
- `backend/app/tests/api/test_cookie_sync_api.py`（新增手动上报用例）
- `extension/cookie-quick-upload/manifest.json`（新增 background + content_scripts）
- `extension/cookie-quick-upload/background.js`（消息处理：抓 cookie / 上报 / 测试连接）
- `extension/cookie-quick-upload/content.js`（可拖动悬浮球 + 上报面板）
- `extension/cookie-quick-upload/options.html` / `options.js`

**完成标准**

- TestClient 走通 `POST /api/cookies/manual`：四字段 upsert（存在更新 `is_new=false`、不存在插入 `is_new=true`），`str_cookie` 拼接正确；无/错 `X-API-Key` 返回 401；cookie 值不入日志
- 扩展在 Chrome 加载后：http/https 页面出现可拖动悬浮球，点击展开面板自动抓当前页面 cookie、填四字段提交写库；抓取为空时「刷新页面并重新获取」可用；「测试连接」经 background 调 `/api/ping` 正确展示联通结果
- 后端测试与编译通过（不涉及前端构建）

### Phase 14：Headers 捕获（chrome.debugger / CDP）✅

> **现状更新（2026-09-03 回写）**：本阶段含 2026-08-27 两次迭代——基础捕获（REQ-010 / AC-008 / AC-009，`chrome.debugger` attach + `Network.enable` + 刷新 + 捕获首个同域名请求头）与「Headers 属性」过滤（AC-010 / AC-011，填属性名则精确捕获请求头含同名键的请求，留空维持原行为），随手动上报写回旧表 `headers` 列。

**目标**

让「Cookie 一键上报」面板能经 `chrome.debugger`（CDP 通道）捕获当前域名 API 的完整请求头（含受保护头，如 Cookie 派生值），与 cookie 一并上报写入旧表 `headers` 列。

**交付物**

- manifest 新增 `debugger` 权限；扩展版本升 1.2.0
- background 新增 `captureHeaders` 消息：`chrome.debugger.attach({tabId})` + `Network.enable` → 自动 reload 当前标签页 → 监听 `Network.requestWillBeSent`（记 requestId→type/url）与 `Network.requestWillBeSentExtraInfo`（requestId→headers）→ 捕获首个同域名 XHR/Fetch 请求的完整请求头 → detach → 经 `chrome.tabs.sendMessage` 通知新注入的 content script；捕获超时/失败给明确提示
- background 支持可选 `headers_filter`（captureHeaders 消息参数）：非空时捕获规则升级为「同域名且请求头存在同名键（精确匹配、大小写不敏感）」，超时提示包含过滤条件
- content 面板新增「Headers 属性」下拉式输入框（`<datalist>` 预置 `token`，可手输），抓取时随 `captureHeaders` 传递；留空不过滤，cookie 仍抓页面全量
- content 面板新增「抓取 Headers」按钮 + 结果展示（来源 URL + 头数量）；上报 body 携带 headers
- 后端：`CookieSyncManualUpload` 新增可选 `headers: dict`；`handle_manual_upload` 将 headers（JSON 序列化）传入 `upsert_by_lookup` 的 headers 参数
- 测试：manual 端点 headers 落库用例（headers 列写入 JSON 字符串；空 headers 不写该列）

**关键文件**

- `extension/cookie-quick-upload/manifest.json`、`background.js`、`content.js`
- `backend/app/schemas/cookie_sync.py`
- `backend/app/services/cookie_sync_service.py`
- `backend/app/tests/api/test_cookie_sync_api.py`

**完成标准**

- 面板「抓取 Headers」→ 页面自动刷新 → 捕获同域名 XHR/Fetch 请求头并显示来源 URL 与头数量
- 面板填「Headers 属性」后抓取仅捕获请求头含同名键（精确、大小写不敏感）的请求；留空维持捕获首个同域名请求
- 上报带 headers → 旧表 `headers` 列写入 JSON 字符串；不抓 headers 时上报不受影响
- 后端测试与编译通过

### Phase 15：生产服务化托管与运维加固 ✅

**目标**

生产后端运行方式由 Windows 服务（NSSM）演进为「交互会话计划任务」单一入口，补齐健康探针、日志轮转、运维文档与修复链路健壮性，保证有头 Chrome / CDP 场景在登录会话可见。

**交付物**

- 统一启动入口 `run_server.py`：先执行 `alembic upgrade head`（失败返回非零退出码中止），再拉起 uvicorn；RotatingFileHandler 写 `runtime/logs/backend.log`（10MB×5 轮转），保留控制台输出
- `start_interactive.bat`：被计划任务调用；优先 `backend\.venv\Scripts\python.exe`（含 alembic/pymysql），无则回退系统 python；stdout/stderr 落 `runtime/logs/boot.log` 供早启诊断
- 计划任务 `SessionBackend-Interactive`（生产唯一入口，交互会话运行）：`schtasks /create` 注册、`/run` 启动、`/end` 停止
- `restart_backend.bat`：`taskkill` 8081 监听进程 → `schtasks /end` 残留实例 → `/run` 重新拉起；直接 `/run` 会遇「任务正在运行中」拒绝，必须先 `/end`
- 生产健康探针 `tools/watchdog.py`：端口 / SQLite / RDS 探活 + 飞书告警（计划任务 `SessionBackend-Watchdog`）
- 运维文档 `docs/OPS-STARTUP.md` / `OPS-BACKUP.md` / `OPS-MONITORING.md` / `OPS-SECURITY.md`：启动入口、备份恢复、监控告警、安全基线
- 修复链路健壮性：停滞 ScriptRun 回收 + 目录锁释放（`health_task_service` 重构）；子进程 stdout 强制 UTF-8 修中文日志乱码（`process_runner`）
- 依赖钉版：`backend/requirements.txt` pin playwright / numpy / Pillow
- README 与启动脚本同步：NSSM 停用（`tools/nssm/` 仅留说明），服务化说明对齐计划任务现状

**关键文件**

- `run_server.py`、`start_interactive.bat`、`restart_backend.bat`
- `tools/watchdog.py`
- `docs/OPS-STARTUP.md`、`docs/OPS-BACKUP.md`、`docs/OPS-MONITORING.md`、`docs/OPS-SECURITY.md`
- `backend/app/services/health_task_service.py`、`backend/app/services/process_runner.py`
- `backend/requirements.txt`、`README.md`

**完成标准**

- 生产后端经计划任务 `SessionBackend-Interactive` 拉起，`restart_backend.bat` 可完整重启（先 `/end` 后 `/run`，不报「任务正在运行中」）
- 日志轮转落 `runtime/logs/backend.log`；`tools/watchdog.py` 探活异常触发飞书告警
- 停滞 ScriptRun 可回收并释放目录锁；中文日志无乱码
- 后端 `pytest` / `compileall` 通过

### Phase 16：自动排障闭环（SCOPE-019 / 020）🔄

**目标**

修复脚本执行返回 `FAIL` / 抛异常 / 返回 `RISK`（风控）时，自动生成自动排障工单（独立于已废弃人工工单），按落库冷却 / 预算节流唤起本机 Claude Code 连接 CDP 现场排障，结论回写 `SOLVED` / `NEED_HUMAN`；`NEED_HUMAN` 关闭调试端口并飞书转人工。**后端已完成并生产生效（SCOPE-019，仓库 main `36ed915`）**；前端列表页（SCOPE-020，P1 排后）待办。

> **现状更新（2026-09-03 部署生效）**：闭环后端合入内部机 `D:\session-maintenance-system`（main `36ed915`），`alembic upgrade head` 至 0015；`SessionBackend-Interactive` 于 09-03 18:34 重启（进程 PID 44192）后新路由才进内存——此前 9/2 13:51 启动的旧进程未加载闭环。openapi 实测新增 `/api/auto-repair-tickets` 与 `/{ticket_id}`，HealthTaskScheduler 每分钟扫描在转；`auto_repair_ticket` 0 条为待点火常态（等首个真实 `FAIL` 触发建档）。运维要点：后端升级必须经计划任务重启才生效（uvicorn 子进程不热加载），核对「是否在跑新代码」以 `openapi.json` 路由清单 + 进程 CreationDate 为准，勿只信磁盘代码版本。SCOPE-020 前端列表页（P1 排后）仍 ⏳。

**交付物**

- `AutoRepairTicket` 模型 + Alembic 迁移 0014；`AutoRepairShopState` 店铺维度排障冷却 / 节流状态 + 迁移 0015
- `auto_repair_ticket_service`：独立会话建档、落库冷却 / 预算节流唤起、结论回写、`NEED_HUMAN` 关 debug 端口 + 飞书转人工
- `agent_repair_dispatcher`：Claude Code CLI 可用性检测 / 超时 / 日志；`FAIL` / `RISK` / `EXCEPTION` 三类故障分流；`TICKET_RESULT` 行锚解析；`REPAIR_TICKET_ID` / 凭据脱敏；店铺维度节流（shop-state 0015）；进行中 agent 保活浏览器不回收
- 人机验证安全护栏：滑块 / 拼图 / 短信 / 扫码 / 设备验证识别即 `NEED_HUMAN` 停止，严禁自动绕过（OUT-004 / 012 / 013）；账号级破坏性操作不无人值守执行
- dispatcher 纯逻辑单测（result parse anchor、RISK prompt 分支、cmd 包装、masking）
- 自动排障工单前端列表页 SCOPE-020（P1 排后，⏳）：查看 `PENDING→RUNNING→SOLVED/NEED_HUMAN` 流转、失败类型与排障结论，人工标记接手 / 关闭

**关键文件**

- `backend/app/models/auto_repair_ticket.py`、`backend/alembic/versions/0014_add_auto_repair_ticket.py`、`0015_add_auto_repair_shop_state.py`
- `backend/app/services/auto_repair_ticket_service.py`、`backend/app/services/agent_repair_dispatcher.py`
- `backend/app/api/routes/auto_repair_tickets.py`
- `backend/app/tests/services/test_auto_repair_ticket_service.py`、`test_auto_repair_dispatcher.py`
- `frontend/src/views/AutoRepairTicketsView.vue`（⏳ 待建）、`frontend/src/api/autoRepairTickets.ts`（⏳ 待建）

**完成标准**

- 脚本 `FAIL` / 异常 / `RISK` 自动建档；冷却期内不重复唤起（shop-state 节流生效）
- dispatcher 成功唤起本机 Claude Code 连 CDP 排障，`TICKET_RESULT` 行锚解析正确回写工单
- `NEED_HUMAN` 停止排障并关 debug 端口 + 飞书告警；排障过程凭据脱敏、不泄密
- dispatcher 单测全绿；后端 `pytest` / `compileall` 通过
- （⏳ 待办）SCOPE-020 前端列表页可查看工单流转、失败类型与结论，支持人工接手 / 关闭

## 6. 数据库表与归属阶段

| 表 / 实体 | 归属阶段 | 说明 |
|---|---|---|
| `health_task` | Phase 2 / 4 | 健康检测任务：检测配置、调度、失败修复、状态 |
| `script_run` | Phase 2 / 5 | 脚本运行实例：状态机、PID、产物、控制 |
| `script_registry` | Phase 2 / 3 | 脚本元信息、版本、启停、运行配置 |
| `profile_registry` | Phase 2 / 3 / 12 | Profile 目录路径、锁状态（`is_locked`/`lock_owner`/`lock_run_id`）、调试端口 `debug_port` |
| `task_run_log` | Phase 2 / 7 | 健康检测、修复脚本运行日志 |
| `env_check_result` | Phase 2 / 7 | 最近一次环境自检结果 |
| `cookie_sync_task` | Phase 7 / 9 | 采集任务：检测配置、调度、同步超时、状态 |
| `cookie_sync_mapping` | Phase 7 / 8 | 采集映射：`(worker_id, domain) → channel/shop_name/mobile_phone/dns` |
| `cookie_sync_job` | Phase 7 / 8 | 扩展采集任务队列：`task_id/worker_id/domains/status` |
| `ods_cookie_playwright` | 外部依赖 | legacy cookie 数据来源；健康检测只读；扩展采集写回（Phase 7 起具备写回能力）；手动上报写回 cookie+headers（Phase 13 / 14） |
| `session_maintenance_task` | 已废弃 | 旧维护任务表，保留数据不再读写 |
| `health_check_config` | 已废弃 | 旧健康检测表，保留数据不再读写 |
| `manual_repair_ticket` | 已废弃 | 旧人工修复工单表，保留数据不再读写 |
| `auto_repair_ticket` | Phase 16 | 自动排障工单：独立于已废弃人工工单，`PENDING→RUNNING→SOLVED/NEED_HUMAN`；迁移 0014 |
| `auto_repair_shop_state` | Phase 16 | 店铺维度排障冷却/节流状态；迁移 0015 |

## 7. 每阶段验证要求

每个 Phase 完成时都必须执行以下验证，缺一项都不算完成：

1. 代码审查：确认行为、边界条件、错误处理和回归风险。
2. 测试验证：补齐与本阶段风险相称的后端测试或接口测试。
3. 编译验证：后端至少通过导入/编译检查，前端至少通过构建检查。
4. 功能验证：对照本 Phase 完成标准做一次真实操作验证。

## 8. 建议执行顺序

> 2026-09-03 回写：仓库现况（main `36ed915`）为 Phase 1-5、7-15 及 Phase 16 后端全部实现。本节给出全新推进顺序与剩余待办排期。

如果按全新项目推进，严格按 Phase 1 到 Phase 16 顺序执行（Phase 16 前端列表页属 SCOPE-020 P1 排后项，可在后端稳定后补）。

基于当前仓库继续推进，已完成与待办如下：

- **已实现**：Phase 1-5（骨架 / 数据模型 / 脚本库与目录 / 健康检测闭环 / 脚本运行）、Phase 7-10（Cookie 采集数据模型 / 扩展 API / 采集闭环 / 前端页面）、Phase 11-14（部署可移植 / 目录库 CDP 调试 / 手动上报扩展 / Headers 捕获）、Phase 15（生产服务化托管与运维加固）、Phase 16 后端（SCOPE-019 自动排障闭环）
- **Phase 6 遗留**：8/25 架构收敛主体已完成；2026-09-02 回潮的四模块（`session_tasks`/`health_checks`/`repairs`/`dashboard`）判废弃残留、待清理（见 Phase 6 现状更新），清理在内部机主工作区执行

后续待办候选（按优先级）：

1. **SCOPE-020 自动排障工单前端列表页**（P1 排后）：对应 Phase 16 前端，查看工单 `PENDING→RUNNING→SOLVED/NEED_HUMAN` 流转、失败类型与排障结论，支持人工接手与关闭
2. **Phase 6 遗留清理**：移除回潮四模块后端路由、前端孤儿 view 及配套测试（内部机执行，避免与主工作区冲突）
3. **完整回归**：后端 `pytest` + `compileall`、前端 `pnpm build`、主链路冒烟（`定时检测→失败→自动排障→回写` 与 Cookie 采集写回），对照 §7 每阶段验证要求

> 说明：auto-repair 闭环（Phase 16）由内部机开发并合入 GitHub `main`（`36ed915`）；E 盘副本为备用工作区，同步以 `origin/main` 为准。扩展本体（Chrome 扩展）已在 `D:\公司小疑问\chrome扩展` 联调验证过，平台侧只维护接收端 API（Phase 8 契约、Phase 10 扩展包入仓、Phase 13/14「Cookie 一键上报」本体扩展）。
