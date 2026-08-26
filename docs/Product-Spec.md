# 产品需求规范：Windows 原生 Session 健康检测与修复系统

## 0. AI 使用说明

- 本文档是产品功能、范围、行为和验收标准的事实来源。
- AI MUST 优先实现 P0。
- AI MUST NOT 实现“不在本版本范围”中明确排除的内容。
- AI MUST 根据“验收标准”判断功能是否完成。
- 如果信息不明确，AI MUST 使用“假设”中的假设；如果仍无法判断，应记录到“待确认问题”，而不是自行扩展需求。

---

## 1. 产品上下文

### 1.1 产品摘要

这是一个部署在单台 Windows 机器上的内部运维系统，用来维护电商平台采集脚本依赖的 session/cookie 登录态。  
系统通过健康检测任务定期或手动检测旧 cookie 是否失效，失败时自动触发本机 Playwright 维护脚本刷新登录态，并通过飞书通知提醒运维人员。遇到短信、扫码、验证码等风控时，不生成人工修复工单，只发送提醒，由运维人员判断后续处理。

### 1.2 用户问题

当前 session 维护依赖分散脚本和人工介入，缺少统一的健康检测编排、失败自动修复、日志追踪和 Profile 管理。结果是 cookie 失效后不能稳定、快速、可追踪地恢复，影响下游采集业务连续性。

### 1.3 目标用户

| 用户类型 | 描述 | 核心需求 |
|---|---|---|
| 内部运维/开发人员 | 负责部署、维护和排障的内部使用者 | 配置健康检测任务、检测登录态、自动触发修复并追踪结果 |

### 1.4 核心价值

把”检测旧 cookie 是否失效 -> 自动触发修复 -> 失败提醒运维 -> 修复后复检恢复”串成一个可视化、可执行、可追踪的闭环，降低登录态失效带来的业务中断时间。

### 1.5 成功标准

| 判断标准 | 目标 / 信号 |
|---|---|
| 健康检测闭环可用 | 可为指定 cookie 定位条件配置检测任务并手动/定时执行，失败后能触发绑定修复脚本 |
| 修复闭环可用 | 修复脚本可成功执行本机脚本，并将成功、失败、风控结果回写系统状态、运行日志与 ScriptRun 实例 |
| 失败提醒可用 | 检测失败或修复遇风控时，通过飞书通知提醒运维人员 |
| 运维可观测性可用 | 用户可在前端查看健康检测任务、脚本运行、Profile、脚本、环境自检和运行日志 |

---

## 2. 范围

### 2.1 本版本范围

| 编号 | 内容 | 优先级 | 备注 |
|---|---|---|---|
| SCOPE-001 | Windows 单机部署的 Session 健康检测与修复系统 | P0 | 不依赖 Docker，使用 CMD/BAT 启动 |
| SCOPE-002 | 健康检测任务 CRUD、启停、克隆、删除、手动检测、手动修复 | P0 | 以健康检测任务为系统核心，绑定修复脚本与 Profile |
| SCOPE-003 | 定时调度 | P0 | APScheduler 扫描启用任务，按 cron 表达式触发检测与修复 |
| SCOPE-004 | Profile 目录注册、校验、锁定/解锁、复检 | P0 | 路径基于 `RUNTIME_ROOT` 解析；锁定由脚本运行持有 |
| SCOPE-005 | 脚本库注册、上传、启停 | P0 | 支持 `MAINTAIN/HEALTH/MANUAL/CUSTOM` |
| SCOPE-006 | 脚本运行实例 ScriptRun | P0 | 记录每次脚本执行：状态、PID、产物、控制（暂停/继续/取消） |
| SCOPE-007 | 环境自检与部署配置展示 | P0 | 覆盖 Python、Playwright、目录、数据库、网络、桌面会话 |
| SCOPE-008 | 运行日志 | P0 | 提供任务/检测/脚本执行的运行记录与筛选 |
| SCOPE-009 | MySQL 数据模型、后端 API、调度能力 | P0 | 使用 APScheduler 扫描启用的健康检测任务 |
| SCOPE-010 | 飞书失败通知 | P0 | 检测失败或修复风控时发送飞书提醒 |
| SCOPE-011 | Cookie 扩展采集任务模块 | P0 | 独立模块，复用健康检测检测逻辑；失效动作=扩展采集；不绑定目录 |
| SCOPE-012 | 采集映射表管理 | P0 | `(worker_id, domain) → (channel/shop_name/mobile_phone/dns)`，写库与反查双向使用 |
| SCOPE-013 | 扩展接入 API 接收端 | P0 | `/api/ping` `/api/request` `/api/tasks` `/api/tasks/{id}/report` `/api/cookies`，`X-API-Key` 鉴权 |
| SCOPE-014 | 采集 cookie 写回旧表 | P0 | 先查后改写回 `ods_cookie_playwright`，填 `cookie` + `str_cookie` |

### 2.2 不在本版本范围

| 编号 | 内容 | 原因 |
|---|---|---|
| OUT-001 | 多节点/分布式执行架构 | 当前方案明确为单台 Windows 机器本机执行 |
| OUT-002 | Docker、容器编排、Windows Service 化托管 | 参考材料明确第一版使用本地目录和 `start_backend.bat` |
| OUT-003 | 面向外部客户的多租户能力 | 当前定位是公司内部运维系统 |
| OUT-004 | 自动绕过短信、扫码、验证码、设备验证 | 风控场景只提醒不自动处理，不做自动化冒险 |
| OUT-005 | 自主 Agent 编排、多 Agent 协作 | 该产品是传统运维系统，不是 Agent 产品 |
| OUT-006 | 重构旧 cookie 表结构 | 沿用既有字段（channel/shop_name/mobile_phone/DNS/cookie/str_cookie 等）；新增扩展采集写回能力，但不新增、不修改旧表列结构 |
| OUT-007 | 人工修复工单、打开修复浏览器、复检闭环 | 已废弃，失败只通过飞书提醒 |
| OUT-008 | 独立"维护任务"模块与旧版"健康检测"模块 | 已废弃，被健康检测任务统一取代 |
| OUT-009 | 同一同事同一域名的多店铺登录态区分 | 本版假设一个 (worker_id, domain) 对应一条业务记录，多店铺场景浏览器侧需分 Profile，暂不处理 |
| OUT-010 | 健康检测任务与采集任务自动联动 | 采集任务独立于健康检测任务，检测任务不自动触发采集，两个模块互不耦合 |
| OUT-011 | 采集任务绑定目录/Profile | 采集任务无目录页，不绑定 ProfileRegistry |

---

## 3. 用户任务

| 编号 | 用户任务 | 用户类型 | 优先级 |
|---|---|---|---|
| TASK-001 | 配置并维护可执行的健康检测任务 | 内部运维/开发人员 | P0 |
| TASK-002 | 为旧 cookie 登录态配置检测并触发自动修复 | 内部运维/开发人员 | P0 |
| TASK-003 | 管理本机 Profile 与脚本资源，保障任务可执行 | 内部运维/开发人员 | P0 |
| TASK-004 | 查看系统健康、部署环境和运行日志，快速定位问题 | 内部运维/开发人员 | P0 |
| TASK-005 | 管理 Cookie 扩展采集：采集任务、映射、扩展接入 | 内部运维/开发人员 | P0 |

---

## 4. 用户流程

### FLOW-001: 配置并执行健康检测任务

**关联任务：** TASK-001  
**优先级：** P0  
**目标：** 让用户创建一条可执行的健康检测任务，并能手动检测和手动修复。

**入口：**  
用户进入”健康检测任务”页面，点击”新增健康检测”。

**主路径：**
1. 用户填写检测名称、cookie 表、渠道、店铺名、手机号、DNS、检测 URL、请求方法、请求头/请求体 JSON、成功/失败规则 JSON。
2. 系统校验必填字段并保存健康检测任务。
3. 用户配置高级调度（cron 表达式、超时、重试次数）与失败修复（自动修复开关、修复脚本、目录、运行模式、脚本配置 JSON）。
4. 用户点击”立即检测”，系统执行检测请求并按规则判断结果。
5. 用户点击”执行修复脚本”，系统锁定 Profile、创建 ScriptRun 实例并执行本机修复脚本。
6. 系统记录运行日志，并根据脚本结果更新任务状态。

**分支路径：**
- 若修复脚本返回 `SUCCESS`，任务状态更新为 `PASS`。
- 若脚本返回 `FAIL`，任务标记为 `FAIL` 并保留失败日志。
- 若脚本返回 `RISK`，任务回到 `PENDING`，系统发送飞书提醒，不生成工单。

**边界情况：**
- Profile 已锁定时，不允许启动新的脚本运行。
- 修复脚本类型不是 `MAINTAIN` 时，不允许绑定为修复脚本。
- 路径非法或跳出 `RUNTIME_ROOT` 时，系统必须拒绝保存/执行。

**完成状态：**
用户可在任务列表、脚本运行页和日志中看到本次执行结果；若失败或风控，系统给出明确状态和飞书提醒。

### FLOW-002: 定时检测发现失效并自动修复

**关联任务：** TASK-002  
**优先级：** P0  
**目标：** 让系统按 cron 定时从旧 cookie 表读取凭证，检测登录态是否有效，并在失败时自动触发修复脚本。

**入口：**  
调度器扫描启用中的健康检测任务，按 cron 表达式触发执行。

**主路径：**
1. 系统按 `cookie_table + channel + shop_name + mobile_phone + DNS` 从旧 cookie 表查询数据。
2. 系统按优先级组装请求头、Cookie、请求体并请求检测 API。
3. 系统根据成功/失败规则判断结果。
4. 若检测通过，系统记录 `PASS` 和日志。
5. 若检测失败，系统标记状态为 `FAIL`，发送飞书通知，并（若配置了自动修复）触发绑定修复脚本。
6. 修复脚本执行完成后，系统更新任务状态为 `PASS` / `FAIL` / `PENDING(RISK)`。

**分支路径：**
- 未启用自动修复时，仅记录检测失败并发送飞书通知，不触发修复。
- 旧表查询失败或检测 API 访问异常时，系统记录失败原因并发送通知。

**边界情况：**
- `http_headers`、旧表 `headers`、`str_cookie`、`cookie JSON` 的组装优先级必须固定。
- 成功规则和失败规则必须允许配置为 JSON 结构。
- 多个任务共享同一修复目录时，依赖 ScriptRun 去重锁避免并发执行。

**完成状态：**
系统留下检测结果与日志；若失效，自动修复链路已被触发并留有 ScriptRun 记录。

### FLOW-003: 环境自检与问题定位

**关联任务：** TASK-005  
**优先级：** P0  
**目标：** 让用户在部署前和排障时快速判断当前 Windows 节点是否具备运行条件。

**入口：**  
用户点击顶部“执行环境自检”按钮或进入“环境自检”页面执行。

**主路径：**
1. 系统检查 Python 虚拟环境、Playwright、Chromium/Chrome、目录权限、数据库连通性、旧表查询能力、当前 Windows 用户、桌面会话和平台网络访问。
2. 系统返回每个检查项的 `PASS/WARN/FAIL` 状态与说明。
3. 用户根据结果进入部署配置或运行日志继续排障。

**分支路径：**
- 桌面会话检查可为 `WARN`，提示通过 RDP 登录后再启动服务。
- 数据库或目录权限失败时，自检整体仍需展示逐项结果，而不是只返回一个总失败。

**边界情况：**
- 自检结果需要可重复执行，并保留最近一次结果。

**完成状态：**
用户可清楚知道当前部署机能否执行健康检测任务以及具体卡在哪个检查项。

### FLOW-004: Cookie 采集任务检测与扩展采集闭环

**关联任务：** TASK-005  
**优先级：** P0  
**目标：** 让用户创建一条 Cookie 采集任务，定时/手动检测旧 cookie 有效性，失效时通过同事浏览器扩展采集新 cookie 写回旧表，实现检测→补采→复检闭环。

**入口：**  
用户进入"Cookie 采集任务"页面，点击"新增采集任务"。

**主路径：**
1. 用户填写采集任务检测配置（名称、cookie 表、channel、shop_name、mobile_phone、DNS、检测 URL、请求方法、请求头/请求体 JSON、成功/失败规则）与调度配置。
2. 系统按 cron 或手动触发执行检测：从旧表按 `cookie_table + channel + shop_name + mobile_phone + DNS` 读取 cookie，组装请求并判定有效性。
3. 若检测通过，任务状态为 `PASS`。
4. 若检测失败，系统通过映射表反向查找该业务记录对应的 `(worker_id, domain)`：
   - 找到映射 → 下发扩展采集任务（task 入队，定向派给该 worker）→ 等待同事扩展上报（`sync_wait_timeout_seconds` 默认 180）→ 按映射写回 `ods_cookie_playwright`（先查后改，填 `cookie` + `str_cookie`）→ 复检。
   - 复检通过 → `PASS`；复检仍失败、等待超时或无映射 → `FAIL` 并发送飞书通知。
5. 系统记录运行日志与采集任务实例状态。

**分支路径：**
- 无映射：检测失败后找不到对应 `(worker_id, domain)`，直接 `FAIL` + 飞书，不触发采集。
- 扩展上报的域名与映射 `dns` 不匹配：丢弃该上报并记 WARN 日志，不写库。
- 采集等待超时：按采集失败处理，任务 `FAIL` + 飞书。

**边界情况：**
- 检测配置与健康检测任务一致，但采集任务不绑定修复脚本与目录。
- 写回旧表采用先查后改（不依赖旧表唯一索引）。

**完成状态：**
用户可在采集任务列表、运行日志看到本次检测、采集、复检结果；失效时若采集成功则状态恢复，否则收到飞书通知。

### FLOW-005: 扩展轮询上报与写库

**关联任务：** TASK-005  
**优先级：** P0  
**目标：** 同事电脑上的扩展按配置周期轮询平台，发现派给自己的采集任务后读取浏览器 cookie 并上报。

**主路径：**
1. 扩展配置 `backendUrl`（平台地址）、`workerId`（采集者编号）、`apiKey`、`domains`。
2. 扩展按轮询周期（默认 30s，Chrome alarm 最小 30s）`GET /api/tasks?worker_id=xxx`。
3. 有任务 → `chrome.cookies.getAll({domain})` 读取该域名 cookie → `POST /api/tasks/{id}/report` 上报。
4. 平台校验 `X-API-Key`，按映射表将 cookie 写回 `ods_cookie_playwright`。

**分支路径：**
- 定时兜底/立即同步走 `POST /api/cookies` 直接推送，同样按映射写库。
- 上报的 `worker_id` 与任务定向 worker 不一致时，以任务定向 worker 为准。

**边界情况：**
- 扩展配置的 `worker_id` 与映射表 `worker_id` 一致，归属才正确。
- 无映射的上报丢弃并记 WARN 日志，不写库。

**完成状态：**
扩展读取的 cookie 已按映射归属写回旧表，采集任务可复检。

---

## 5. 功能需求

### 5.1 前端设计与交互规范

#### IA-001: 信息架构

- 整体采用后台运维工作台结构：左侧固定导航栏 + 右侧主内容区。
- 左侧导航 MUST 按以下顺序提供一级入口：
  - 健康检测任务
  - Cookie 采集任务
  - 脚本库
  - 目录库
  - 脚本运行
  - 运行日志
  - 环境自检
  - 部署配置
- 主内容区顶部 MUST 包含页面标题、页面说明和全局快捷操作区。
- 顶部快捷操作 MUST 至少包含：
  - 执行环境自检
  - 上传脚本

#### IA-002: 视觉与布局方向

- 第一版前端不是营销页，定位是高密度运维后台。
- 视觉风格 MUST 接近现有原型：深色左侧导航、浅色主背景、白色卡片面板、表格为主、状态色明确。
- 页面内容 MUST 优先服务“看状态、做动作、查原因”，不为装饰牺牲信息密度。
- 状态颜色 SHOULD 保持强语义：
  - 成功/可用：绿色
  - 失败/异常：红色
  - 警告：橙色
  - 风控：紫色
  - 中性/禁用：灰色
- 所有核心页面 SHOULD 使用卡片 + 工具栏 + 表格/时间线结构，不引入复杂多栏嵌套。

#### IA-003: 共用交互组件

- 列表页 MUST 统一包含：
  - 页面标题与说明
  - 顶部操作按钮
  - 搜索框或状态筛选
  - 数据表格
  - 空状态
- 详情查看 SHOULD 使用弹窗或详情面板，而不是跳转新页面。
- 新增/编辑操作 MUST 使用表单弹窗，保留当前列表上下文。
- 危险或不可逆动作 SHOULD 使用强调色按钮或二次确认。
- 所有操作完成后 MUST 给出即时反馈，如成功提示、失败提示、风控提示。

#### IA-004: 页面级设计要求

| 页面 | 布局重点 | 必须展示的信息 | 关键操作 |
|---|---|---|---|
| 健康检测任务 | 三 Tab 配置 + 主表格 | 检测任务名、cron、cookie 定位信息、检测 API、失败执行脚本、启动目录、运行模式、状态、最近检测/修复时间 | 新增、编辑、立即检测、执行修复脚本、查看日志、启停、克隆、删除 |
| 脚本库 | 主表格 + 上传入口 | 脚本名、脚本编码、类型、平台、目录、主文件、版本、状态、运行配置 | 上传、详情、启停 |
| 目录库 | 主表格 | Profile Key、相对路径、绝对路径预览、状态、锁状态、最近验证 | 登记、复检、锁定、解锁 |
| 脚本运行 | 统计卡片 + 实例表格 | run_id、健康检测任务、脚本、启动目录、运行模式、状态、开始时间、运行时长、PID | 查看详情、查看日志、暂停/继续、取消 |
| 运行日志 | 筛选栏 + 时间线/表格 | 时间、类型、状态、标题、消息、关联对象 | 筛选、查看详情 |
| 环境自检 | 自检结果卡片/列表 | 检查项、状态、说明、明细 | 执行自检、查看详情 |
| 部署配置 | 配置说明页 | 根目录、运行目录、关键子目录、启动方式、端口、当前运行用户提示 | 查看配置 |
| Cookie 采集任务 | 任务列表 + 映射管理 + 扩展接入 | 采集任务名、cron、cookie 定位信息、检测 API、状态、最近检测/采集时间；映射：worker_id、domain、channel、shop_name、mobile_phone、dns | 新增、编辑、启停、删除、立即检测、查看日志；映射增删改；扩展接入信息展示 |

#### IA-005: 表格列与详情弹窗要求

- 健康检测任务列表 MUST 包含：
  - 检测任务名称
  - cron 表达式
  - cookie 定位信息（cookie 表、channel/shop_name/mobile_phone/DNS）
  - 检测 API
  - 失败执行脚本
  - 启动目录
  - 运行模式
  - 状态
  - 最近检测时间
  - 最近修复时间
- 健康检测任务详情/编辑弹窗 MUST 使用三 Tab：
  - Tab 1 检测配置：检测名称、cookie 表、channel、shop_name、mobile_phone、DNS、检测 API、请求方法、请求头/请求体 JSON、成功/失败规则 JSON
  - Tab 2 高级调度：启用、cron 表达式、超时时间、失败重试次数、最近/下次检测时间
  - Tab 3 失败修复：启用自动修复开关、维护脚本（仅 `MAINTAIN`）、启动目录、运行模式、脚本配置 JSON、执行超时
- 脚本运行列表 MUST 包含：
  - run_id
  - 健康检测任务
  - 脚本
  - 启动目录
  - 运行模式
  - 状态（PENDING/RUNNING/PAUSED/CANCELING/CANCELED/SUCCESS/FAIL/RISK）
  - 开始时间
  - 运行时长
  - PID
- Profile 列表 MUST 包含：
  - Profile Key
  - 相对路径
  - 绝对路径预览
  - 状态
  - 锁状态
  - 最近验证时间
  - 备注
- 脚本库列表 MUST 包含：
  - 脚本名称
  - 脚本编码
  - 脚本类型
  - 平台
  - 脚本目录
  - 主文件
  - 版本
  - 状态
  - 说明
  - 运行配置（default_run_mode/supports_pause/supports_cancel/default_timeout_seconds）

#### IA-006: 表单与弹窗设计要求

- 健康检测任务弹窗 MUST 使用三 Tab，包含：
  - Tab 1 检测配置：检测名称、cookie 表、channel、shop_name、mobile_phone、DNS、请求方法、检测 API、请求 headers JSON、请求 body JSON、成功规则、失败规则
  - Tab 2 高级调度：启用开关、cron 表达式、检查超时秒数、失败重试次数
  - Tab 3 失败修复：自动修复开关、维护脚本（仅 `MAINTAIN`）、启动目录、运行模式、脚本配置 JSON、执行超时
- 登记 Profile 弹窗 MUST 包含：
  - Profile Key
  - 相对路径
  - 备注
- 上传脚本弹窗 MUST 包含：
  - 脚本名称
  - 脚本编码
  - 脚本类型
  - 平台
  - 版本
  - 主文件
  - 脚本包
  - 脚本目录
  - 说明

#### IA-007: 页面状态设计

- 每个核心页面 MUST 处理以下状态：
  - 加载中
  - 空状态
  - 请求失败
  - 操作成功提示
  - 权限/前置条件不满足
- 任务执行相关页面 MUST 额外处理：
  - Profile 已锁定
  - 脚本执行中（ScriptRun RUNNING/PAUSED）
  - 风控（RISK，仅提醒）
- 环境自检页面 MUST 逐项展示 `PASS/WARN/FAIL`，不能只给总结果。
- 运行日志页面 SHOULD 同时支持表格式检索和时间线式阅读。

### REQ-001: 健康检测任务管理

**优先级：** P0  
**关联任务：** TASK-001, TASK-002  
**关联流程：** FLOW-001, FLOW-002  

**用途：**  
系统核心模块，将检测、调度、修复统一为一条健康检测任务。

**行为：**  
用户可创建、编辑、启停、克隆、删除健康检测任务；查看列表与详情；手动执行检测；手动执行修复脚本；查看执行时间线。

**规则：**
- MUST 使用 `health_task_code/health_task_name/enabled/cookie_table/channel/shop_name/mobile_phone/dns/check_url/http_method/http_headers/http_body/success_rule/failure_rule` 字段表达检测配置。
- MUST 使用 `cron_expression/check_timeout_seconds/retry_count` 字段表达高级调度。
- MUST 使用 `auto_repair_enabled/repair_script_id/repair_directory_id/repair_run_mode/repair_script_config/repair_timeout_seconds/repair_cron_expression` 字段表达失败修复。
- MUST 仅允许绑定 `MAINTAIN` 类型修复脚本。
- MUST 在执行修复前检查 Profile（目录）是否已锁定。
- MUST 支持状态 `PENDING/PASS/FAIL/DISABLED`，运行结果状态 `SUCCESS/FAIL/RISK`。
- MUST 检测失败时发送飞书通知；修复遇 `RISK` 时不生成工单，只发送提醒。
- SHOULD 支持克隆任务以快速复制配置。
- SHOULD 支持独立修复 cron（`repair_cron_expression`）：调度器按该表达式周期性触发修复脚本；未配置时检测失败即时触发。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| health_task_name | string | Yes | 非空 |
| cookie_table | string | Yes | 默认 `ods_cookie_playwright` |
| channel | string | Yes | 非空 |
| shop_name | string | No | 可空 |
| mobile_phone | string | No | 可空 |
| dns | string | No | 可空 |
| check_url | string | Yes | 合法 URL |
| http_method | string | Yes | `GET/POST` 等合法 HTTP 方法 |
| http_headers | json | No | 合法 JSON |
| http_body | json | No | 合法 JSON |
| success_rule | json | No | 合法 JSON |
| failure_rule | json | No | 合法 JSON |
| cron_expression | string | No | 合法 cron 表达式 |
| auto_repair_enabled | boolean | No | 默认 false |
| repair_script_id | number | No | 必须指向已启用 `MAINTAIN` 脚本 |
| repair_directory_id | number | No | 指向目录库中的目录 |
| repair_run_mode | string | No | `HEADLESS/HEADED` 或空 |

**输出 / 结果：**
- 健康检测任务被创建、更新、启停、克隆或删除。
- 执行后产生最近检测/修复时间、运行状态、ScriptRun 实例和日志。

**状态：**
- 默认：显示任务列表。
- 加载：列表或执行请求处理中。
- 空状态：无任务时显示空提示。
- 错误：表单校验失败、检测请求失败、修复失败或目录锁定时给出明确错误。
- 成功：任务保存成功或执行成功，状态同步刷新。

**验收标准：**
- [ ] AC-001: Given 用户填写完整检测任务信息, when 点击保存, then 系统成功创建任务并在列表显示。
- [ ] AC-002: Given 任务绑定了被锁定的目录, when 用户执行修复, then 系统拒绝执行并返回锁冲突错误。
- [ ] AC-003: Given 修复脚本返回 `RISK`, when 任务完成, then 任务状态回到 `PENDING` 且发送飞书提醒、不生成工单。
- [ ] AC-004: Given 检测失败且配置了自动修复, when 检测完成, then 系统自动触发修复脚本并创建 ScriptRun 实例。

### REQ-002: 脚本运行实例管理

**优先级：** P0  
**关联任务：** TASK-003  
**关联流程：** FLOW-001, FLOW-002  

**用途：**  
追踪每次脚本执行的生命周期，提供运行状态、产物、日志和控制能力。

**行为：**  
用户可查看脚本运行实例列表、详情、实时日志、result.json；对运行中的脚本执行暂停/继续/取消。

**规则：**
- MUST 使用 `run_id/health_task_id/health_task_code/script_id/script_code/directory_id/directory_key` 表达实例关联。
- MUST 使用 `run_mode/script_config/timeout_seconds` 表达运行配置。
- MUST 支持状态 `PENDING/RUNNING/PAUSED/CANCELING/CANCELED/SUCCESS/FAIL/RISK`。
- MUST 记录 `pid/start_time/end_time/duration_ms` 与产物路径（artifact_dir/log_file/stdout_file/stderr_file/result_json）。
- MUST 在脚本执行前锁定目录，结束后释放目录锁。
- MUST 支持暂停/继续/取消：通过 `control.json`（`{“pause”:..,”cancel”:..}`）控制脚本行为。
- SHOULD 同一脚本+目录存在进行中实例时，去重阻止重复执行。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| run_id | string | Yes | `run_<uuid12>` 唯一 |
| script_id | number | Yes | 指向脚本库脚本 |
| run_mode | string | Yes | `HEADLESS/HEADED` |
| health_task_code | string | No | 可空，触发来源 |

**输出 / 结果：**
- 创建 ScriptRun 实例、写入控制文件与产物、记录状态变化。
- 暂停/继续/取消更新实例状态与日志。

**验收标准：**
- [ ] AC-001: Given 用户对运行中的实例点击暂停, then 实例状态变为 `PAUSED` 且 `control.json` 写 `pause:true`。
- [ ] AC-002: Given 用户取消运行实例, then 进程树被终止、目录锁释放、实例状态变为 `CANCELED`。
- [ ] AC-003: Given 同一脚本+目录存在 `RUNNING` 实例, then 新的执行被去重阻止。

### REQ-003: Profile 目录管理

**优先级：** P0  
**关联任务：** TASK-003  
**关联流程：** FLOW-001, FLOW-002  

**用途：**  
管理部署机本地浏览器用户目录，保证脚本复用稳定登录态。

**行为：**  
用户可注册 Profile（目录库）、查看相对路径和绝对路径预览、锁定/解锁、复检；可绑定脚本（该脚本以该目录为默认启动目录执行）。

**规则：**
- MUST 仅保存相对 `RUNTIME_ROOT` 的路径，不直接持久化绝对路径。
- MUST 禁止 `..`、路径穿越和危险字符。
- MUST 支持状态 `MISSING/READY/LOCKED/RISK/CORRUPTED`。
- MUST 在执行脚本前检查锁状态；锁由 ScriptRun 实例持有。
- SHOULD 显示最近验证时间和备注。
- SHOULD 支持绑定脚本：一个 Profile 可关联多个脚本，脚本执行时优先使用该目录作为启动目录。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| profile_key | string | Yes | 唯一 |
| relative_path | string | Yes | 相对路径，必须在 `RUNTIME_ROOT` 下 |
| note | string | No | 可空 |
| 绑定脚本 | script_code[] | No | 可绑定多个脚本 |

**输出 / 结果：**
- Profile 注册或更新成功。
- 用户可看到绝对路径预览与当前锁状态。

**状态：**
- 默认：显示 Profile 列表。
- 加载：校验、锁定或解锁处理中。
- 空状态：暂无 Profile。
- 错误：路径非法、Profile 不存在、锁冲突。
- 成功：状态、锁定标识和验证时间更新。

**验收标准：**
- [ ] AC-001: Given 用户提交相对路径, when 保存 Profile, then 数据库只保存相对路径且页面显示绝对路径预览。
- [ ] AC-002: Given Profile 正被某运行实例锁定, when 另一实例尝试执行, then 系统因锁冲突拒绝执行。
- [ ] AC-003: Given 用户点击复检, when 复检成功, then Profile 状态变为 `READY` 且更新时间刷新。

### REQ-004: 脚本库管理

**优先级：** P0  
**关联任务：** TASK-003  
**关联流程：** FLOW-001  

**用途：**  
管理维护脚本、手动修复脚本与其他扩展脚本的元信息和 Python 脚本文件。

**行为：**  
用户可查看脚本列表、上传脚本、查看详情、启停脚本。

**规则：**
- MUST 支持脚本类型 `MAINTAIN/HEALTH/MANUAL/CUSTOM`。
- MUST 支持平台枚举 `COMMON/KUAISHOU/TAOBAO/TMALL/ALIMAMA/JD/PDD`。
- MUST 将上传脚本保存到 `runtime\\scripts\\uploaded\\{script_code}\\{version}`。
- MUST 仅接受 `.py` 脚本文件上传，脚本元信息由上传表单填写。
- MUST 校验上传后缀、文件名、大小和落盘路径安全。
- SHOULD 展示脚本主文件、版本、说明和绝对路径预览。
- SHOULD 支持运行配置：默认运行模式、默认 CDP 端口、默认超时、暂停/取消支持开关。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| script_name | string | Yes | 非空 |
| script_code | string | Yes | 唯一 |
| script_type | string | Yes | 必须为支持的枚举 |
| platform | string | Yes | 必须为支持的枚举 |
| version | string | Yes | 非空 |
| script_file | file | Yes | 仅 `.py` |
| description | string | No | 可空 |
| default_run_mode | string | No | `HEADLESS/HEADED` |
| default_cdp_port | number | No | 1-65535 |
| default_timeout_seconds | number | No | 默认 600 |
| supports_pause/cancel | boolean | No | 控制能力开关 |

**输出 / 结果：**
- 脚本元信息写入注册表。
- 脚本文件保存到运行目录。

**状态：**
- 默认：脚本列表可浏览。
- 加载：上传或启停处理中。
- 空状态：暂无脚本。
- 错误：上传非法、文件名非法、路径越界、字段冲突。
- 成功：脚本上传成功并可用于绑定。

**验收标准：**
- [ ] AC-001: Given 用户上传合法 `.py` 脚本并填写完整元信息, when 保存, then 系统将其落到 `runtime\\scripts\\uploaded\\...` 并登记元信息。
- [ ] AC-002: Given 用户上传非 `.py` 文件或非法文件名, when 上传, then 系统拒绝保存并返回错误。
- [ ] AC-003: Given 任务选择维护脚本, when 绑定脚本, then 只能选择 `MAINTAIN` 类型脚本。

### REQ-005: 环境自检

**优先级：** P0  
**关联任务：** TASK-004  
**关联流程：** FLOW-003  

**用途：**  
在部署和排障时验证当前 Windows 节点的运行条件。

**行为：**  
系统执行一组自检项，逐项展示结果和说明，并保留最近一次自检结果。

**规则：**
- MUST 覆盖 Python、venv、Playwright、Chromium/Chrome、运行目录权限、数据库连接、旧表查询、当前 Windows 用户、桌面会话、平台网络。
- MUST 逐项返回 `PASS/WARN/FAIL`。
- MUST 提供“执行自检”和“查看最新结果”能力。
- SHOULD 对桌面会话给出通过 RDP 登录后启动服务的提示。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| 无 | - | No | 系统自检 |

**输出 / 结果：**
- 返回每个检查项状态、提示文案和明细。

**状态：**
- 默认：展示最近一次自检。
- 加载：自检执行中。
- 空状态：尚无自检结果。
- 错误：某检查项执行异常时给出错误说明。
- 成功：结果列表完整返回。

**验收标准：**
- [ ] AC-001: Given 用户执行环境自检, when 检查完成, then 页面逐项显示 `PASS/WARN/FAIL` 和说明。
- [ ] AC-002: Given 桌面会话不可用, when 自检完成, then 页面以 `WARN` 提示通过 RDP 登录后启动服务。
- [ ] AC-003: Given 旧表不可查询, when 自检执行, then 页面明确标记数据库或旧表项为 `FAIL`。

### REQ-006: 部署配置与运行日志

**优先级：** P0  
**关联任务：** TASK-004  
**关联流程：** FLOW-003  

**用途：**  
让用户看到部署约束、目录结构、启动方式，并用日志追踪所有关键动作。

**行为：**  
系统展示部署根目录、运行目录、脚本目录、Profile 目录、日志目录、制品目录、启动方式和端口；同时提供运行日志查询。

**规则：**
- MUST 展示 `DEPLOY_ROOT`、`RUNTIME_ROOT` 和关键子目录。
- MUST 提供 `start_backend.bat` 启动示例。
- MUST 记录 `CHECK/REPAIR` 日志类型（健康检测、修复脚本执行）。
- MUST 支持日志状态 `SUCCESS/FAIL/RISK/WARN` 和条件筛选。
- SHOULD 提供关联健康检测任务、脚本运行实例、日志文件、截图、trace 信息。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| run_type | string | No | 可按枚举筛选 |
| status | string | No | 可按枚举筛选 |
| health_task_code/run_id | string | No | 可选 |
| keyword | string | No | 可选 |
| time_range | datetime range | No | 可选 |

**输出 / 结果：**
- 展示部署配置说明。
- 返回日志列表和筛选结果。

**状态：**
- 默认：展示配置和最近日志。
- 加载：日志查询中。
- 空状态：无日志记录。
- 错误：日志查询失败。
- 成功：配置和日志正常展示。

**验收标准：**
- [ ] AC-001: Given 用户进入部署配置页, when 页面加载, then 用户能看到目录结构、端口和启动方式说明。
- [ ] AC-002: Given 系统执行过任务或检测, when 用户进入日志页, then 用户能按类型、状态、关键字筛选日志。
- [ ] AC-003: Given 某任务执行失败, when 用户查看日志详情, then 用户能定位到关联任务与失败信息。

### REQ-007: Cookie 采集任务管理

**优先级：** P0  
**关联任务：** TASK-005  
**关联流程：** FLOW-004, FLOW-005  

**用途：**  
独立模块，复用健康检测任务的检测配置与调度逻辑，但失效动作改为扩展采集（同事浏览器扩展补采 cookie 并写回旧表），不绑定脚本与目录。

**行为：**  
用户可创建、编辑、启停、克隆、删除采集任务；手动/定时检测；检测失效时触发扩展采集并复检；支持**手动执行扩展采集**（不经过检测，直接触发扩展补采闭环）；查看采集任务运行日志与状态。

**规则：**
- MUST 复用健康检测任务的检测配置字段：`cookie_table/channel/shop_name/mobile_phone/dns/check_url/http_method/http_headers/http_body/success_rule/failure_rule`。
- MUST 复用调度字段：`enabled/cron_expression/check_timeout_seconds/retry_count`。
- MUST 失效动作 = 扩展采集：通过映射表反向查找 `(worker_id, domain)`，下发采集任务（定向派给该 worker），等待上报（`sync_wait_timeout_seconds` 默认 180），写回旧表，复检。
- MUST NOT 绑定修复脚本与目录（无 `repair_script_id` / `repair_directory_id`），无目录锁冲突。
- MUST 支持状态 `PENDING/PASS/FAIL/DISABLED/SYNCING`；`SYNCING` 表示等待扩展上报。
- MUST 最终 `FAIL` 时发送飞书通知（无映射、等待超时、复检仍失败均视为 `FAIL`）。
- MUST 无映射时直接 `FAIL` + 飞书，不触发采集。
- MUST 支持手动执行扩展采集：不经过检测，直接反查映射下发采集任务进入 `SYNCING`，等待上报、写回、复检闭环与检测失效后的采集完全一致；任务已在 `SYNCING` 时跳过重复触发；无映射时返回明确错误（不动任务状态，因非检测失败）。
- SHOULD 支持克隆采集任务以复制配置。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| cookie_sync_task_name | string | Yes | 非空 |
| cookie_table | string | Yes | 默认 `ods_cookie_playwright` |
| channel | string | Yes | 非空 |
| shop_name | string | No | 可空 |
| mobile_phone | string | No | 可空 |
| dns | string | No | 可空 |
| check_url | string | Yes | 合法 URL |
| http_method | string | Yes | `GET/POST` 等合法 HTTP 方法 |
| http_headers / http_body | json | No | 合法 JSON |
| success_rule / failure_rule | json | No | 合法 JSON |
| cron_expression | string | No | 合法 cron 表达式 |
| sync_wait_timeout_seconds | number | No | 默认 180 |

**输出 / 结果：**
- 采集任务被创建、更新、启停、克隆或删除。
- 执行后产生最近检测/采集时间、运行状态、日志；失效时触发扩展采集并留下采集记录。

**状态：**
- 默认：显示采集任务列表。
- 加载：检测或采集处理中。
- 空状态：无采集任务时显示空提示。
- 错误：表单校验失败、检测请求失败、无映射、采集超时给出明确错误。
- 成功：任务保存成功或检测/采集完成，状态同步刷新。

**验收标准：**
- [ ] AC-001: Given 用户填写完整采集任务信息, when 点击保存, then 系统成功创建任务并在列表显示。
- [ ] AC-002: Given 检测失效且存在对应映射, when 检测完成, then 系统下发采集任务并进入 `SYNCING` 状态，上报后写回旧表并复检。
- [ ] AC-003: Given 检测失效且无对应映射, when 检测完成, then 任务直接 `FAIL` 并发送飞书通知，不触发采集。
- [ ] AC-004: Given 采集等待超过 `sync_wait_timeout_seconds`, when 超时, then 任务 `FAIL` 并发送飞书通知。
- [ ] AC-005: Given 用户点击"执行修复", when 存在对应映射, then 系统直接下发采集任务进入 `SYNCING`，上报后写回旧表并复检；无映射时返回明确错误。

### REQ-008: 采集映射管理

**优先级：** P0  
**关联任务：** TASK-005  
**关联流程：** FLOW-004, FLOW-005  

**用途：**  
维护采集者到业务记录的映射：`(worker_id, domain) → (channel, shop_name, mobile_phone, dns)`。写库时用正向映射填旧表字段；任务触发时用反向映射查该问哪位同事采集。

**行为：**  
用户可对映射表增删改查，查看某 worker 的最近上报时间。

**规则：**
- MUST 以 `(worker_id, domain)` 为唯一键，一个组合对应一条业务记录。
- MUST 支持增删改查；删除映射前需检查是否有采集任务依赖该业务记录。
- MUST 扩展上报时校验上报域名与映射 `dns` 一致，不一致则丢弃并记 WARN 日志。
- SHOULD 展示每个 `worker_id` 的最近上报时间与上报条数。
- 可建必可删：映射支持删除路径。

**输入：**

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| worker_id | string | Yes | 唯一（与 domain 组合） |
| domain | string | Yes | 合法域名 |
| channel | string | Yes | 非空 |
| shop_name | string | No | 可空 |
| mobile_phone | string | No | 可空 |
| dns | string | Yes | 应与 domain 一致 |
| remark | string | No | 可空 |

**输出 / 结果：**
- 映射保存或更新成功，可用于写库与反查。

**状态：**
- 默认：显示映射列表。
- 加载：增删改查处理中。
- 空状态：暂无映射。
- 错误：`(worker_id, domain)` 重复、dns 与 domain 不一致、被采集任务依赖。
- 成功：映射生效。

**验收标准：**
- [ ] AC-001: Given 用户新增映射, when 保存, then 映射列表出现且可被任务反查、扩展上报正向映射。
- [ ] AC-002: Given 用户提交重复的 `(worker_id, domain)`, when 保存, then 系统拒绝并提示冲突。
- [ ] AC-003: Given 某映射被采集任务依赖, when 删除, then 系统阻止并提示依赖。

### REQ-009: 扩展接入 API 接收端

**优先级：** P0  
**关联任务：** TASK-005  
**关联流程：** FLOW-005  

**用途：**  
实现 Chrome 扩展（Cookie 同步助手）契约的接收端接口，让同事电脑上的扩展可连接平台完成任务轮询与上报。

**行为：**  
平台提供扩展契约五条接口；校验 `X-API-Key`（`COOKIE_SYNC_API_KEY` 留空时关闭鉴权，仅限本地联调）；接收上报 cookie 按映射写回旧表；无映射上报丢弃并记日志。

**规则：**
- MUST 实现 `GET /api/ping`（无鉴权，扩展测试连接用）。
- MUST 实现 `POST /api/request`（采集脚本触发同步：`{domains, worker_ids}` → `{task_ids}`）。
- MUST 实现 `GET /api/tasks?worker_id=xxx`（返回派给该采集者的待处理任务：`{tasks:[{task_id, worker, domains, status}]}`）。
- MUST 实现 `POST /api/tasks/{task_id}/report`（扩展上报：`{cookies, worker_id, collected_at}`）。
- MUST 实现 `POST /api/cookies`（扩展定时兜底/立即同步直接推送：`{domains, cookies, worker_id, collected_at}`）。
- MUST 除 `/api/ping` 外所有接口校验 `X-API-Key`（`COOKIE_SYNC_API_KEY` 留空时关闭鉴权，见下条），密钥来自 `.env`。
- MUST `COOKIE_SYNC_API_KEY` 为空时关闭鉴权（仅限本地联调）；配置非空时所有非 ping 接口强制校验（生产必填）。
- MUST 上报 cookie 脱敏，日志不得明文记录 cookie 值。
- MUST 无映射的上报丢弃并记 WARN 日志，不写库。
- MUST 上报 `worker_id` 与任务定向 worker 不一致时，以任务定向 worker 为准。

**输入：**（见扩展契约 body 结构）

| 字段 | 类型 | 必填 | 校验规则 |
|---|---|---:|---|
| X-API-Key | header | 条件 | `COOKIE_SYNC_API_KEY` 非空时必填，必须等于其值；留空时关闭鉴权 |
| domains | string[] | Yes | 非空 |
| worker_id | string | No | 空则归 `unknown` |
| cookies | object[] | Yes | `chrome.cookies` 原生字段（name/value/domain/path/secure/httpOnly/expirationDate/sameSite） |
| worker_ids | string[] | No | `/api/request` 定向采集者列表 |

**输出 / 结果：**
- 扩展可轮询、上报、直推；采集任务可完成"下发→上报→写库→复检"闭环。

**验收标准：**
- [ ] AC-001: Given `COOKIE_SYNC_API_KEY` 已配置, when 请求无或错 `X-API-Key`, then 非 ping 接口返回 401。
- [ ] AC-002: Given 扩展上报无映射的域名, when 上报, then cookie 不写库并记 WARN 日志。
- [ ] AC-003: Given 采集任务进入 `SYNCING`, when 扩展轮询, then 扩展能拿到定向任务并上报，平台写回旧表。

### AI 能力规格（每个 AI 功能必填）

本产品当前版本不包含 AI 功能。

**AI 护栏（绝不能做）：**
- 不适用。

---

## 6. 数据模型

### 6.1 核心实体

| 实体 | 描述 | 关键字段 |
|---|---|---|
| HealthTask | 健康检测任务 | `health_task_code`, `health_task_name`, `cookie_table`, `channel`, `shop_name`, `mobile_phone`, `dns`, `check_url`, `http_method`, `cron_expression`, `auto_repair_enabled`, `repair_script_id`, `repair_directory_id`, `status` |
| ScriptRun | 脚本运行实例 | `run_id`, `health_task_code`, `script_id`, `script_code`, `directory_id`, `directory_key`, `run_mode`, `status`, `pid`, `artifact_dir`, `result_json` |
| ScriptRegistry | 脚本注册信息 | `script_code`, `script_name`, `script_type`, `platform`, `script_dir`, `main_file`, `version`, `enabled`, `default_run_mode` |
| ProfileRegistry | 本机 Profile 目录注册信息 | `profile_key`, `relative_path`, `status`, `is_locked`, `lock_owner`, `lock_run_id` |
| TaskRunLog | 运行日志 | `run_id`, `task_id`, `health_task_code`, `run_type`, `status`, `title` |
| EnvCheckResult | 环境自检结果 | `check_key`, `check_name`, `status`, `message` |
| LegacyCookieRecord | 旧 cookie 表记录 | `channel`, `shop_name`, `mobile_phone`, `DNS`, `cookie`, `headers`, `str_cookie`, `str_1`, `str_2`, `file` |
| CookieSyncTask | 采集任务 | `cookie_sync_task_code`, `cookie_sync_task_name`, `cookie_table`, `channel`, `shop_name`, `mobile_phone`, `dns`, `check_url`, `http_method`, `http_headers`, `http_body`, `success_rule`, `failure_rule`, `cron_expression`, `sync_wait_timeout_seconds`, `status` |
| CookieSyncMapping | 采集映射 | `worker_id`, `domain`, `channel`, `shop_name`, `mobile_phone`, `dns`, `remark` |
| CookieSyncJob | 扩展采集任务队列 | `task_id`, `worker_id`, `domains`, `status`, `created_at`, `finished_at` |

### 6.2 实体关系

| 关系 | 描述 |
|---|---|
| HealthTask references ScriptRegistry | 一个健康检测任务绑定一个修复脚本 |
| HealthTask references ProfileRegistry | 一个健康检测任务绑定一个启动目录 |
| ScriptRun belongs to HealthTask | 一个脚本运行实例关联一个健康检测任务 |
| ScriptRun references ScriptRegistry | 一个运行实例关联一个脚本 |
| ScriptRun references ProfileRegistry | 一个运行实例锁定并占用一个目录 |
| TaskRunLog references HealthTask/ScriptRun | 日志可挂接健康检测任务或脚本运行 |
| HealthTask reads LegacyCookieRecord | 健康检测从旧 cookie 表读取凭证数据 |
| CookieSyncTask reads/writes LegacyCookieRecord | 采集任务从旧表读 cookie 检测，采集成功后写回旧表 |
| CookieSyncTask references CookieSyncMapping | 检测失败时按映射反查 `(worker_id, domain)` |
| CookieSyncJob belongs to CookieSyncTask | 一次采集下发对应一个任务实例，定向派给某 worker |

### 6.3 数据规则

- 所有 runtime 路径在数据库中只保存相对路径，运行时统一基于 `RUNTIME_ROOT` 解析绝对路径。
- 创建健康检测任务时，修复配置可暂不绑定脚本/目录；启用自动修复时必须有可用脚本和可绑定目录。
- 创建或上传的资源必须规划删除/停用路径；本版至少支持脚本启停、健康检测任务启停/删除、ScriptRun 取消，不允许只有新增没有停用。
- 目录在脚本运行期间必须锁定，运行结束释放，避免并发使用。
- 旧 cookie 表的主键和结构不由本系统修改，只按既有字段读写；扩展采集写回采用先查后改，不依赖旧表唯一索引。
- 扩展上报 cookie 写回旧表必须经映射表；无映射的上报丢弃并记 WARN 日志。
- 扩展接口除 `/api/ping` 外必须校验 `X-API-Key`（`COOKIE_SYNC_API_KEY` 留空时关闭鉴权，仅限本地联调）；密钥在 `.env`。
- 采集任务不绑定目录，无锁冲突。
- 日志必须脱敏，不能明文记录 cookie、凭证或密码。

---

## 7. 外部依赖

| 编号 | 依赖 | 用途 | 是否必需 | 备注 |
|---|---|---|---:|---|
| DEP-001 | Windows 桌面环境 / Windows Server | 本机执行脚本 | Yes | 当前版本限定单机 Windows |
| DEP-002 | Python + FastAPI | 后端 API 与任务服务 | Yes | 参考材料建议栈 |
| DEP-003 | MySQL | 系统表与旧 cookie 表 | Yes | 包含本系统库和 legacy cookie 库 |
| DEP-004 | Playwright | 自动维护脚本执行 | Yes | 使用本机浏览器 Profile |
| DEP-005 | Vue 3 + TypeScript + Vite | 前端管理界面 | Yes | 参考原型与开发文档建议 |
| DEP-006 | APScheduler | 定时执行健康检测 | Yes | 扫描启用检测任务 |
| DEP-007 | Chrome/Chromium | 浏览器执行环境 | Yes | 脚本可能需要 headed 模式 |
| DEP-008 | 飞书机器人 Webhook | 失败/风控通知 | Yes | 检测失败与修复风控时推送提醒 |
| DEP-009 | Chrome 扩展（Cookie 同步助手）+ 同事电脑浏览器 | 采集同事浏览器登录态 cookie | Yes | 扩展本体装在同事机器，平台仅实现接收端 API |
| DEP-010 | 阿里云 RDS MySQL 写权限 | 扩展采集 cookie 写回 `ods_cookie_playwright` | Yes | 需 RDS 账号具备 UPDATE/INSERT 权限 |

---

## 8. 非功能需求

| 类别 | 要求 | 优先级 |
|---|---|---|
| 性能 | 单次健康检测请求默认超时 20 秒；列表页在常规数据量下应支持秒级加载 | P0 |
| 安全 | 凭证加密存储；接口返回和日志输出必须脱敏；上传脚本必须校验后缀、大小、manifest 和路径穿越；扩展接口除 `/api/ping` 外必须校验 `X-API-Key`（`COOKIE_SYNC_API_KEY` 留空时关闭鉴权，仅限本地联调） | P0 |
| 隐私 | 不在日志、页面和错误信息中泄露 cookie、密码、token 等敏感字段 | P0 |
| 兼容性 | 第一版仅要求支持 Windows 部署节点；前端需支持桌面浏览器访问 | P0 |
| 可靠性 | 脚本执行必须记录 stdout/stderr、result.json、运行状态；风控和失败必须可追踪和可恢复 | P0 |
| 可访问性 | 基础表单和操作按钮应具备明确标签与状态提示 | P1 |

---

## 9. 完成定义

MVP 完成条件：

- [ ] 所有 P0 requirements 已实现
- [ ] 所有 P0 acceptance criteria 已通过
- [ ] 所有 P0 user flows 可以端到端完成
- [ ] 主要错误状态、空状态、加载状态已处理
- [ ] Product Spec 和 Design Spec 中的 P0 内容保持一致

---

## 10. 假设与待确认问题

### 10.1 假设

| 编号 | 假设 | 假设依据 | 错误风险 |
|---|---|---|---|
| ASM-001 | 当前系统为内部使用，不需要复杂权限体系和多租户隔离 | 参考材料只描述内部运维场景 | 若实际有多角色隔离要求，前后端设计都要补权限模型 |
| ASM-002 | 第一版允许用户通过前端直接维护部署配置展示信息，但核心路径仍来自 `.env` | 开发文档给出 `.env` 与部署配置页面 | 若部署配置需要真正在线编辑并即时生效，需增加配置持久化和校验 |
| ASM-003 | 调度范围仅覆盖启用的健康检测任务，按 cron 表达式触发检测与修复；未配置 cron 的任务每隔至少 5 分钟兜底执行一次 | 文档明确 APScheduler 负责扫描健康检测任务 | 若需要更复杂的调度（间隔、时段），调度模型需扩展 |
| ASM-004 | 风控场景（短信、扫码、验证码、设备验证）只发送飞书提醒，不做人工修复工单闭环 | 用户已确认废弃人工修复模块 | 若未来需要人工接管流程，需重新引入工单与复检机制 |
| ASM-005 | 同一同事同一域名的多店铺登录态本版不区分，一个 (worker_id, domain) 对应一条业务记录 | 用户确认"先不处理" | 若实际需区分，需引入 profile 级 worker 或采集标识，映射模型需扩展 |

### 10.2 待确认问题

| 编号 | 问题 | 是否阻塞 | 备注 |
|---|---|---:|---|
| Q-001 | 是否需要登录鉴权、用户账号体系和操作审计？ | Yes | 当前原型未体现权限边界 |
| Q-002 | 健康检测任务是否需要批量导入/导出？ | No | 当前只覆盖页面手工维护，已支持克隆 |
| Q-003 | 部署配置页面中的 `PUT /api/deploy/config` 是否真的允许修改运行配置，还是仅展示说明？ | Yes | 影响配置存储方式与运行时刷新机制 |
| Q-004 | ~~旧 cookie 表的写回策略是否只允许脚本直接写库，还是也需要后端代写接口？~~ 已定 | No | 已定：由平台后端代写（Cookie 扩展采集写回旧表） |
| Q-006 | `ods_cookie_playwright` 是否有可依赖的更新键/时间戳字段，RDS 账号是否具备写权限？ | Yes | 影响写回实现与数据新鲜度标记 |
| Q-007 | 同事电脑到平台 8081 的网络可达性、防火墙放行与 API Key 分发方案？ | Yes | 扩展需跨机器访问平台 |
| Q-005 | 前端是否要支持更细的日志详情页、截图预览和 trace 下载？ | No | 当前原型仅展示列表和基础详情能力 |

---

## 11. Agent 系统规格（仅 agent 产品填）

不适用。本产品不是 agent / 自主系统，而是传统 Windows 运维管理系统。
