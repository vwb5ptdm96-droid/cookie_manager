# Product Spec Changelog

## 2026-09-03 · 自动排障闭环（Claude Code 排障）

- 新增：SCOPE-019 自动排障闭环（后端）——修复脚本返回 `FAIL`/抛异常/返回 `RISK`(风控) 时自动生成自动排障工单（独立于已废弃人工工单），按落库冷却/预算节流唤起本机 Claude Code 连接 CDP 现场排障，结果回写 SOLVED/NEED_HUMAN，NEED_HUMAN 关端口 + 飞书转人工；SCOPE-020 自动排障工单前端列表页（P1 排后）。
- 新增：TASK-007、FLOW-007、REQ-011、数据模型 `AutoRepairTicket`、DEP-012（Claude Code CLI）。
- 反转：ASM-004 由「风控仅飞书提醒、不做人工修复闭环」改为「风控进入自动排障闭环，遇人机验证即停转人工」；AI 能力规格由「本版本不包含 AI」改为引入单一定向排障 agent；§11 Agent 系统规格由「不适用」改为定向排障 agent 规格（运行边界/工具集/安全护栏）。
- 定界：OUT-004/012/013——排障 agent 禁止自动绕过或完成人机验证（滑块/拼图/短信/扫码/设备验证），识别即 NEED_HUMAN 停止；账号级破坏性操作不无人值守执行；多 Agent 协作与自主编排仍不在范围（OUT-005）。
- 影响：人工修复工单（ManualRepairTicket）维持废弃（OUT-007 不变）；自动排障工单用独立新模型，不影响既有健康检测/修复/采集主链路。内部机先行草稿（dispatcher/extension 坏实现，commit b78cc23）按本文档重建。

## 2026-09-01 · Windows Service 化托管（范围更新）

- 新增：SCOPE-018 Windows Service 化托管——生产后端注册为 Windows 服务（NSSM `SessionBackend`）：开机自启、崩溃自动重启、日志轮转；启动入口 `run_server.py`（先 `alembic upgrade head` 再起 uvicorn），路径自身推导不绑定盘符。
- 调整：SCOPE-001 备注由「使用 CMD/BAT 启动」改为「本地目录 + CMD/BAT 启动，生产托管为 Windows 服务」；OUT-002 移除「Windows Service 化托管」（已实现，转入 SCOPE-018），仅保留 Docker、容器编排不在范围，原因更新为 Windows 原生部署形态。
- 影响：纯部署形态变更，不改变任何 API 与功能行为；运维命令见 README「以 Windows 服务运行后端」一节。

## 2026-09-01 · 修复：无 cron 任务不再自动兜底调度

- 修复：ASM-003 原「未配置 cron 的任务每隔至少 5 分钟兜底执行一次」与前端「留空为仅手动触发」语义冲突——用户将任务设为手动（cron 留空）后仍被调度器每 5 分钟自动执行。改为「未配置 cron 的任务仅手动触发，调度器跳过不自动执行」。
- 调整：`scheduler_service.py` 健康检测与 Cookie 采集两处扫描删除无 cron 的 5 分钟兜底分支；`cron_expression` 为空的任务完全跳过调度，只在用户手动触发时执行。
- 影响：改前启用且 cron 为空的任务仅 1 个（天猫-品牌引擎-检查，id=32），无其他任务依赖兜底逻辑，改后不影响有 cron 的正常任务。

## 2026-08-27 · Headers 属性过滤（扩展抓取精确定位关键请求）

- 新增：手动上报扩展「抓取 Cookie + Headers」支持「Headers 属性」过滤——面板提供可下拉的属性名输入框（预置 `token`，可手输），填了则捕获规则从「首个同域名请求」升级为「同域名且请求头存在同名键（精确匹配、大小写不敏感）」的请求；不填维持原行为。
- 边界：过滤仅作用于 headers 捕获阶段，cookie 仍抓当前页面全量；过滤条件不随上报入库（`POST /api/cookies/manual` body 不变）。
- 新增：FLOW-006 主路径/分支补过滤流程与超时提示（含过滤条件说明）；REQ-010 规则补「Headers 属性」MUST；输入表补 `headers_filter`（面板参数，不入库）；AC-010（填属性时精确捕获/无匹配超时）、AC-011（留空维持原行为）。

## 2026-08-27 · 抓取合并：Cookie + Headers 一键同时获取

- 修复：REQ-010「抓取 Headers」触发刷新后未重新抓 cookie，导致上报时无 Cookie（headers 路径与刷新路径各做半件事）。改为一次点击同时抓取 cookie 与请求头——headers 捕获完成/失败均重新抓取当前页面 cookie；按钮改为「抓取 Cookie + Headers（将刷新页面）」。
- 调整：FLOW-006 主路径第 3 步、REQ-010 规则、AC-008 描述同步为「同时抓取 cookie 与请求头」。

## 2026-08-27 · Headers 捕获（chrome.debugger / CDP）

- 新增：REQ-010/SCOPE-017 支持「抓取 Headers」——面板按钮经 `chrome.debugger`（CDP 通道）attach 当前标签页 + `Network.enable`，自动刷新页面，捕获首个同域名 XHR/Fetch 请求的完整请求头（含受保护头，如 Cookie 派生值），面板展示来源 URL 与头数量。
- 新增：headers 随上报入库——`POST /api/cookies/manual` body 新增可选 `headers`（object），后端写入旧表 `headers` 列（JSON 字符串）；空则不写该列。
- 新增：AC-008（Headers 捕获）、AC-009（headers 落库）；FLOW-006 主路径/分支补「抓取 Headers」流程与捕获超时。
- 说明：debugger attach 期间 Chrome 顶部显示调试提示条、F12 受限（自用场景可接受，README 注明）。

## 2026-08-27 · 一键上报悬浮球交互 + 后端联通测试

- 调整：REQ-010/SCOPE-017 交互入口从「扩展 popup」改为「页面内可移动悬浮球」——content script 向 http/https 页面注入悬浮球、可拖动、点击展开上报面板，无需在扩展栏找图标；cookie 读取/上报/测试连接均经 background 转发（content script 的 fetch 受页面 CORS 限制）。
- 新增：后端联通测试——面板内「测试连接」按钮经 background 调 `GET /api/ping`，展示后端可达/不可达及原因。
- 调整：FLOW-006 入口与主路径、REQ-010 行为/规则/状态/验收标准；新增 AC-006（测试连接）、AC-007（悬浮球拖动）；AC-001 改为悬浮球展开自动抓取。

## 2026-08-27 · 手动 Cookie 上报扩展

- 新增：SCOPE-017 手动 Cookie 上报扩展——独立 MV3 Chrome 扩展，一键抓取当前页面 cookie，手动填写 channel/shop_name/mobile_phone/dns 写回 `ods_cookie_playwright`；不经映射表、无采集者概念；重复上传按四字段 upsert（存在更新、不存在插入）；没抓到 cookie 时支持刷新当前页面重抓。
- 新增：TASK-006（手动上传当前页面 cookie 入库）、FLOW-006（手动上报流程）、REQ-010（手动 Cookie 上报扩展，含"刷新页面并重新获取"交互与脱敏展示）。
- 新增：扩展接入 API 第六接口 `POST /api/cookies/manual`（REQ-009 更新）：body `{channel, shop_name, mobile_phone, dns, cookies, collected_at}` → `{ok, stored, is_new}`；不经映射表、按四字段 upsert 写回旧表；与现有接口一致走 `X-API-Key` 鉴权。
- 新增：DEP-011（Cookie 一键上报扩展 + 本机浏览器）、ASM-006（四字段 upsert 语义假设）。
- 调整：REQ-009 扩展契约从五条扩为六条，补充手动上报规则与字段（channel/dns 必填、shop_name/mobile_phone 可空）；数据模型补手动上报写回旧表关系与数据规则。
- 定界：扩展命名「Cookie 一键上报」；纯粹独立、不挂平台前端——后端地址与 API Key 在扩展自身 options 页维护，平台前端扩展接入展示区仅保留任务驱动扩展「Cookie 同步助手」（IA-004 保持原样）。

## 2026-08-26 · 部署可移植化 + 目录库 CDP 调试

- 新增：SCOPE-015 部署配置可移植化——启动链路全部从 `.env` 读取（`APP_PORT` 端口、`DEPLOY_ROOT/RUNTIME_ROOT/DATABASE_URL` 相对路径自动解析、`CHROME_PATH` Chrome 路径），清理前端硬编码端口（扩展接入展示改动态 origin、开发代理按 `.env` 解析），部署机无 E 盘、默认端口被占时改 `.env` 即可启动。
- 新增：SCOPE-016 目录库 CDP 调试功能——每目录存默认调试端口 `debug_port`，「打开调试」拉起带该目录（`--user-data-dir`）的可见 Chrome 并暴露 CDP 端口，「关闭调试」清理对应 Chrome 进程；目录锁定时禁用；Chrome 路径走 `CHROME_PATH`（未配置自动探测）。
- 调整：REQ-003 Profile 目录管理新增 `debug_port` 字段与调试规则/验收（AC-004/005/006）；REQ-006 部署配置新增 `.env` 可移植约束；数据模型 ProfileRegistry 新增 `debug_port`。
- 调整：Q-007 明确服务端口由 `APP_PORT` 决定，扩展接入地址按当前 origin 动态展示。

## 2026-08-25 · Cookie 扩展采集迭代

- 新增：Cookie 扩展采集任务模块（独立模块，复用健康检测检测逻辑，失效动作=扩展采集，不绑定目录；导航位于健康检测任务之后）。
- 新增：采集映射表（`(worker_id, domain) → channel/shop_name/mobile_phone/dns`，写库正向映射 + 任务触发反向查询双向使用）。
- 新增：扩展接入 API 接收端（`/api/ping`、`/api/request`、`/api/tasks`、`/api/tasks/{id}/report`、`/api/cookies`，非 ping 接口 `X-API-Key` 鉴权）。
- 新增：采集 cookie 写回 `ods_cookie_playwright`（先查后改，填 `cookie` + `str_cookie`）。
- 新增：REQ-007 采集任务管理、REQ-008 采集映射管理、REQ-009 扩展接入 API；数据模型新增 CookieSyncTask/CookieSyncMapping/CookieSyncJob。
- 调整：OUT-006 明确为不重构旧表结构，但新增写回能力；Q-004 已定（后端代写接口）。
- 删除：原方案"脚本库 CUSTOM 采集通道条目"（管理面收敛到采集任务模块内，不新增导航之外的入口）。
- 说明：同一同事同一域名的多店铺登录态本版不处理，一个 (worker_id, domain) 对应一条业务记录（ASM-005）。

## 2026-08-25

- **Spec 漂移回写**：补充 REQ-001 修复 cron（`repair_cron_expression`）、REQ-003 Profile 绑定脚本、REQ-004 脚本运行配置（`default_run_mode/default_cdp_port/default_timeout_seconds/supports_pause/cancel`）、ASM-003 无 cron 任务 5 分钟兜底调度。
- **重大架构收敛**：产品从"维护任务 + 旧健康检测 + 人工修复工单 + 总览"四模块架构，收敛为以"健康检测任务 + 脚本运行"为核心的新架构。
- 删除：总览 Dashboard（REQ-001）、维护任务模块（REQ-002）、旧健康检测模块（REQ-003）、人工修复工单模块（REQ-006）。
- 新增：REQ-001 健康检测任务管理（检测/调度/修复三 Tab 配置、克隆、删除）、REQ-002 脚本运行实例管理（ScriptRun 状态机、暂停/继续/取消、去重锁）。
- 调整：REQ-003 Profile 目录管理（去掉绑定任务字段）、REQ-004 脚本库（补充运行配置列）、REQ-005 环境自检、REQ-006 部署配置与运行日志（run_type 收敛为 CHECK/REPAIR）。
- 失败处理：检测失败或修复遇风控 `RISK` 时，只发送飞书通知，不再生成人工修复工单。
- 导航收敛为 7 项：健康检测任务 / 脚本库 / 目录库 / 脚本运行 / 运行日志 / 环境自检 / 部署配置。
- 全局快捷操作收敛为：执行环境自检、上传脚本。

## 2026-06-30

- 初版创建 `Product-Spec.md`，基于开发文档和原型整理系统定位、范围、流程、功能需求、数据模型和验收标准。
- 补充前端设计与交互规范，明确后台信息架构、视觉方向、页面布局、表格列、详情弹窗、表单字段和关键状态。
- 创建 `Design-Brief.md`，明确视觉系统、页面规格、组件规范、状态样式、文案语气、响应式和实现约束。
- 创建 `DEV-PLAN.md`，基于 Product Spec 与 Design Brief 拆分 8 个可独立验收的开发阶段，并补充当前稳定技术栈版本、数据库表归属和开发规则。
