# 站点值班 Agent · 角色 × 页面 × 工具 × 成功证据

> **状态**：决策已锁定（2026-09-20）· 实现未开始  
> **关系**：补强而非替代 `AGENT-MAINTENANCE-LAYER.md`。Agent 从「FAIL 才上场的排障工人」扩成「这个站点的值班内核」。  
> **继承**：Repairer 的复检 PASS、人机红线、Profile 锁、禁止扫其它工单，一律不放宽。  
> **产品真源**：侧边栏 9 页见 `frontend/src/router/index.ts`；API 前缀见 `docs/功能清单.md` §5。

---

## 0. 一句话

这个网站已经是 Session 维护的控制面。Agent 变大，是因为它开始**操作整张导航**，不是再做一个通用编码 OS。

- 内核：产品后端（调度、锁、工单、复检）
- 系统调用：现有 `/api/*`（禁止裸 bash 漫游）
- 大脑：可插拔模型（当前 DeepSeek + Claude CLI 外包，后续可换成进程内 loop）
- 驾驶舱：现有 9 页 + `/auto-repair-tickets` 工作台

一个 harness、四套工具箱（按角色焊死）。对话可追问；**追问默认不改脚本**。

---

## 1. 四个角色

| 角色 | 中文 | 何时出场 | 写权限 | 成功证据（硬） |
|------|------|----------|--------|----------------|
| Watcher | 值班 | 定时早报、工作台随时问、异常只读调查 | **无** | 引用可核验的任务/运行/锁/工单数字；禁止口述「今天都正常」 |
| Dispatcher | 调度 | 修复终态 FAIL/EXCEPTION/RISK；辅路径卡死工单；**采集失败另立工单** | 只建单/节流/飞书，不改脚本、不动浏览器 | 工单状态机合法；冷却/预算命中有记录；不扫其它店 |
| Repairer | 排障 | 仅本单 RUNNING；FAIL/EXCEPTION 全量；RISK 诊断-only | 本单脚本 + 本单 CDP；复检未过默认回滚 | **绑定健康检测复检 = PASS** 才可 SOLVED |
| Collector | 采集异常 | 仅 `kind=cookie_sync` 工单 | 可重派补采、请求采集复检；**不得** CDP / 改脚本 / 写映射 | **采集任务复检 PASS**（cookie 已写回）才可 SOLVED；无映射 → NEED_HUMAN |
| SRE | 运维 | 环境/进程/库/日志异常；人工问「服务怎么了」 | 默认无；回收停滞 / 重启后端需 **human_gate**（可进工具，须工作台确认） | 诊断能指到具体检查项/日志/端口；重启须有确认记录 |

角色互斥规则：

1. 同一回合只启用一套工具箱。工作台若未绑定工单 → Watcher；绑了 RUNNING 工单 → Repairer（追问仍只读，除非显式「进入排障回合」）。
2. Dispatcher 不是对话人格，是平台代码。Agent 不得自己 `INSERT` 工单表。
3. 采集失败 **另立工单**（`kind=cookie_sync`），由 Collector 处理。成功定义是采集复检 PASS，**不**套用健康检测复检 PASS，**不**进 Repairer。
4. 无单对话（Watcher）**等进程内 loop（S3）** 再接工作台；禁止把现有 Claude CLI 外包扩成全站问答。
5. 早报 **只工作台**，不发飞书（NEED_HUMAN / 排障失败飞书不变）。

---

## 2. 继承的硬规则（LOCKED，本文不得放宽）

| # | 规则 |
|---|------|
| 1 | Repairer SOLVED ⇔ 绑定健康检测复检 PASS。页面观感、自述、`--skip-db` 都不算 |
| 2 | RISK：可拉起，只诊断判级；不改脚本、不重跑修复、不过验 |
| 3 | 人机（滑块/拼图/短信/扫码/设备验证/封禁）→ 立即 NEED_HUMAN + 飞书 |
| 4 | Profile 目录锁：Agent 全流程持有；同目录串行 |
| 5 | 只处理实例包里的 `ticket_code`；禁止扫其它工单/切店 |
| 6 | 禁止改 `backend/app/core`、迁移、`.env`、启动脚本；禁止 cookie/密码明文进事件 |
| 7 | 检测 FAIL 但未跑修复 → 不开 Repairer |
| 8 | 健康任务不自动联动采集任务（OUT-010）；采集失败走独立 `cookie_sync` 工单，不触发健康修复脚本 |

---

## 3. 主矩阵

图例：`R` 只读 · `W` 可写（经产品 API）· `G` 需人工闸 · `—` 不可见/不可用。

### 3.1 角色 × 页面

| 页面 | 路由 | Watcher | Dispatcher | Repairer | Collector | SRE |
|------|------|---------|------------|----------|-----------|-----|
| 健康检测任务 | `/health-tasks` | R 列表/时间线/最近结果 | 读修复终态以建排障单 | R 本单绑定任务；W 仅「请求平台复检」 | — | R |
| Agent 工作台 | `/auto-repair-tickets` | R 全局状态/早报（S3 起无单问答） | W 建单（代码） | R+W 本单事件/结论；追问默认 R | R+W 本采集单事件/结论 | R 卡死/超时 |
| Cookie 采集任务 | `/cookie-sync-tasks` | R 任务/job/映射是否缺失 | 读失败原因以建 `cookie_sync` 单 | — | R 本任务；W 重派补采 + 采集复检；映射 CRUD 仅人 | R |
| Profile 目录 | `/profiles` | R 锁/debug_port | — | R 本单 profile；W 仅平台已开的 debug | — | R；关端口 G |
| 脚本库 | `/scripts` | R 元数据/启停状态 | — | W 仅本单目标文件 + 备份/diff/回滚 | — | R |
| 脚本运行 | `/script-runs` | R 列表/卡死 | 读修复 run 终态 | R 本单触发 run；W 按实例包重跑修复 | — | R；取消 G |
| 运行日志 | `/logs` | R 筛选失败 | — | R 本单相关日志尾 | R 本任务相关 | R |
| 环境自检 | `/environment` | R 最近结果 | — | — | — | R；触发自检 W |
| 部署配置 | `/deploy` | R 路径/端口（无密钥） | — | — | — | R |

### 3.2 角色 × 工具 × 成功证据

工具名是 harness 契约，实现应对现有 API，不新开旁路写库。

#### Watcher（只读值班）

| 工具 | 背后 API / 数据 | 典型问法 | 成功证据 |
|------|-----------------|----------|----------|
| `site_ops_summary` | health_tasks 状态计数 + cookie_sync 状态 + script_runs 非终态 + auto_repair counts + profile 锁 | 「今天跑得怎么样」 | 返回带时间窗的计数；每项有 `as_of` |
| `site_list_health_tasks` | `GET /api/health-tasks` | 「哪些店检测 FAIL」 | 列表字段与后台页一致（code/shop/status/last_result） |
| `site_health_timeline` | `GET /api/health-tasks/{id}/timeline` | 「这店昨晚为啥红」 | 时间线事件可在 `/health-tasks` 点开对上 |
| `site_list_cookie_sync` | `GET /api/cookie-sync-tasks` + jobs | 「采集卡在哪」 | 区分：检测 FAIL / 无映射 / job 超时 / 复检失败 |
| `site_list_script_runs` | `GET /api/script-runs` | 「有没有卡死的修复」 | RUNNING 超时用平台同一套 `created_at` 时区规则 |
| `site_list_tickets` | `GET /api/auto-repair-tickets` | 「Agent 在忙什么」 | 不得返回其它店诊断正文以外的 cookie |
| `site_get_logs` | `GET /api/logs` | 「最近一次失败日志」 | 截断 + 脱敏；禁止全文倾倒撑爆上下文 |
| `site_env_last_check` | `GET /api/environment/checks` | 「节点还活着吗」 | 引用最近一次自检项，不编造 |
| `site_deploy_info` | `GET /api/deploy` | 「现在听哪个端口」 | 只读；无 `.env` 值 |

Watcher 禁止：`script_edit`、`cdp_*`、`run_repair`、`ticket_close`、取消运行、开关 Chrome。

早报最低结构（`site_ops_summary`）：

```text
时间窗: [北京时间 yesterday 18:00, now]
健康检测: 启用 n / 最近 FAIL n / 修复触发 n
采集任务: 启用 n / 补采中 n / 无映射 n / 复检失败 n
脚本运行: RUNNING n（其中疑超时 n）/ RISK n
目录锁: 持锁 n
Agent: RUNNING n / PENDING n / 今日 SOLVED n / NEED_HUMAN n
需要人看: 最多 5 条，每条带页面深链
```

#### Dispatcher（平台代码，不进模型工具箱）

| 动作 | 触发 | 成功证据 |
|------|------|----------|
| 建 `auto_repair_ticket` | 修复 ScriptRun 终态 FAIL/EXCEPTION/RISK | 一店一单冷却；实例包字段齐全 |
| 拉起 Repairer | PENDING→RUNNING 且持锁 | pid/事件流开始；失败则 FAILED 可解释 |
| 建 `cookie_sync` 工单 | 采集：无映射 / job 超时 / 复检失败 | 与排障单分 `kind`；不持 Profile 锁；不进 CDP |
| 拉起 Collector | `kind=cookie_sync` 且 PENDING | 无脚本备份；无 debug 端口 |
| 辅路径补扫 | RUNNING 超时 / PENDING 过久 | 与现 `reap_stuck_auto_repair_tickets` 一致；采集单同样超时 FAILED |
| 飞书 | NEED_HUMAN / 排障或采集失败 | 脱敏摘要；**早报不发飞书** |

#### Repairer（现有排障工人，工具化）

| 工具 | 背后能力 | 何时可用 | 成功证据 |
|------|----------|----------|----------|
| `ticket_pack_get` | 本单实例包 | 开工第一件事 | 缺 CDP/脚本/健康任务 → 停，NEED_HUMAN |
| `cdp_inspect` | `tools/cdp_inspector.py` + 本单 port | 非 RISK 全量；RISK 只看 | 截图/URL/DOM 摘要进事件；禁止连其它 port |
| `cdp_click_safe` | 可逆关闭弹窗 | 非验证码 | 操作前后截图；识别人机则停 |
| `script_read` / `script_edit` | 本单 `runtime/scripts/...` | FAIL/EXCEPTION；RISK **无此工具** | 改前备份；unified diff 必显；禁止改 core/.env |
| `repair_rerun` | 按实例包重跑绑定 MAINTAIN | 有 diff 或仅浏览器操作后 | 新 ScriptRun id；不释放他人锁 |
| `health_recheck` | `execute_check(..., follow_up=False)` 绑定任务 | 准备关单前 | PASS 才允许 `ticket_conclude(SOLVED)` |
| `ticket_conclude` | `TICKET_RESULT` 结构化（不要 json 信封正则） | 终态 | SOLVED 必须附 `recheck_run_id` + PASS；否则平台拒绝 |

Repairer 失败分类（取代「无有效结果」一刀切）：

| 码 | 含义 | 工单 |
|----|------|------|
| `NO_CONCLUSION` | loop 结束无结构化结论 | FAILED，可辅路径重试 |
| `TIMEOUT` | 超预算 | FAILED + 飞书 |
| `RECHECK_FAIL` | 自报修好但复检未过 | 回滚脚本；继续或 NEED_HUMAN |
| `HUMAN_GATE` | 人机/封禁 | NEED_HUMAN，关 debug |
| `RISK_DIAGNOSIS` | RISK 分支结束 | NEED_HUMAN（即使模型想 SOLVED） |

#### Collector（采集异常，另立工单）

与 Repairer **分工具箱**。实现上可同表加 `kind=cookie_sync`，或独立表；产品上必须分列，SOLVED 语义不得混用。

| 工具 | 背后能力 | 何时可用 | 成功证据 |
|------|----------|----------|----------|
| `sync_pack_get` | 本采集单：task、job、映射是否存在、失败原因 | 开工第一件事 | 缺 task_id → NEED_HUMAN |
| `sync_mapping_get` | `GET /api/cookie-sync-mappings` 按 domain/worker | 始终只读 | 无映射不得编造 worker；结论 NEED_HUMAN，等人去映射页 |
| `sync_dispatch` | 现有采集任务「修复」= 重派扩展 job | 有映射且 job 超时/失败 | 新 job id；不改扩展源码 |
| `sync_recheck` | 采集任务检测复检（写回后） | 准备关单前 | PASS 才允许 SOLVED |
| `ticket_conclude` | 结构化结论 | 终态 | SOLVED 必须附采集复检 PASS；禁止引用健康检测 PASS |

Collector 禁止：`cdp_*`、`script_edit`、`repair_rerun`、映射 CRUD、写 `ods_cookie_playwright` 旁路。

#### SRE（节点运维）

| 工具 | 背后 API | 闸 | 成功证据 |
|------|----------|----|----------|
| `site_env_run_check` | `POST /api/environment/checks` | 无（只跑检查） | 新结果 id，页面可打开 |
| `site_explain_backend` | 日志尾 + `/api/health` + 8081 | 无 | 「进程活/死、最近 traceback 签名」，不给密码 |
| `site_recycle_stale_runs` | 现有回收停滞 ScriptRun | **G** | 回收条数 + 释放的 profile 锁 |
| `site_restart_backend` | `restart_backend.bat` | **G（工作台确认后执行）** | 确认人/时间入事件；重启后 `/api/health` 探活才算完成 |

SRE 禁止：改脚本、开 Chrome、写 cookie 表、Alembic、读 `.env`。无确认记录不得重启。

---

## 4. 工作台交互（页面怎么变大）

现路由 `/auto-repair-tickets` 保留，语义从「排障单列表」扩成「值班台」。交互细节见 [SITE-OPERATOR-UX.md](./SITE-OPERATOR-UX.md)。

| 列/区 | 现在 | 锁定 |
|-------|------|------|
| 左：工单列表 | 有 | 置顶「今日值班摘要」（只工作台、不飞书）；筛选含 `kind=auto_repair \| cookie_sync` |
| 中：时间线 | 思考/工具/截图/diff/复检 | Watcher 查询工具（S3 起）；Repairer / Collector 分列事件 |
| 右：对话 | 可追问、不改脚本 | **S3 进程内 loop 之前**：只允许已有本单追问（不改脚本）。无单 Watcher 问答 **不准**接现有 Claude CLI。S3 后：未选单 = Watcher；选中排障单 / 采集单 = 本单问答；显式按钮才进入 Repairer 写回合 |
| SRE 闸 | 无 | 重启后端、回收停滞：工作台确认按钮 → 才调工具 |

深链约定：早报每条带 `path + query`（如 `/health-tasks?keyword=店铺`），Agent 不发明不存在的页。

---

## 5. 触发面（相对原 LOCKED 的增量 · 2026-09-20 已拍板）

| 触发 | 原 LOCKED | 现锁定 |
|------|-----------|--------|
| 修复 FAIL/EXCEPTION → Repairer | 主路径 | 保持 |
| 修复 RISK → 诊断-only | 选项 B | 保持 |
| 定时补未结/卡死工单 | 辅路径 | 保持；采集单同样补扫 |
| 定时早报 Watcher | 无 | **新增**，只工作台，不飞书；可手动刷新摘要 |
| 工作台无单 Watcher 问答 | 无 | **S3 进程内 loop 后**才接；此前不做 |
| 采集失败 → Collector | 明确不做 | **另立 `cookie_sync` 工单** |
| 仅检测 FAIL 未修 → Agent | 明确不做 | 保持不做 |
| 后端 500 / 列表挂掉 | 无 | SRE 只读解释；重启走 human_gate |

---

## 6. 明确仍不做

- 通用编码 agent（乱扫仓库、改 backend、装依赖）
- 自动过滑块/接码
- 把 grok-build / OpenWebUI / LibreChat 嵌进本仓库
- Watcher/SRE/Collector 共用 Repairer 写工具
- 采集失败套用健康检测复检 PASS
- 无人工闸的重启后端、`--hard` 回滚 Profile
- Agent 擅自写采集映射或旁路写 cookie 表
- 用现有 Claude CLI 外包做全站无单问答
- 多 Agent 繁殖（子 agent 非本阶段）

---

## 7. 落地切片（大设计，小切口）

与代码现状对齐，不推翻 Slice A–E。

| 切片 | 内容 | 验收 |
|------|------|------|
| S0 | 现网缝合线：json 结论 unwrap、created_at 时区、ticket cwd、脚本丢失防护 | 真实 log 能抽出结论；不再误超时回收 |
| S1 | 本文 + LOCKED 回写 + 值班 SOP（本文档已完成决策） | 四条拍板写进基线 |
| S2 | Watcher **只读 API** + 工作台早报（无模型问答） | 早报数字与页面一致 |
| S3 | 进程内 loop：Repairer 迁入 + 无单 Watcher 问答；`ticket_conclude` 结构化；CLI json 降为兼容层 | SOLVED 必须带对应复检；无单问答不改脚本 |
| S4 | `cookie_sync` 工单 + Collector 工具箱 | 无映射 → NEED_HUMAN；有映射重派后采集复检 PASS 才 SOLVED |
| S5 | SRE 自检/解释；回收停滞 / 重启后端 **G** | 无确认不能重启；重启后 health 探活 |

S0 仍是当前生产第一刀。S2 是「管整个站」的第一可见产品（早报）。S3 才打开全站对话。

---

## 8. 已拍板（2026-09-20）

1. 采集失败：**另立工单**（Collector，不进 Repairer）。  
2. 早报：**只工作台**，不发飞书。  
3. 无单对话：**等进程内 loop（S3）**。  
4. 重启后端：**可进工具，必须人工确认（human_gate）**。

回写：`AGENT-MAINTENANCE-LAYER.md` §12 站点值班；`SOP-值班手册.md`；排障仍用 `SOP-操作手册.md`。实现未开始前，不得扩大写权限。
