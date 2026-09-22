# Dispatcher 改造差距清单

> **对照基线**  
> - 共识：`AGENT-MAINTENANCE-LAYER.md`  
> - 增强路径：`ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md`（含 §6.1 探活）  
> - 代码：`backend/app/services/agent_repair_dispatcher.py`、`auto_repair_ticket_service.py`、`health_task_service.py` 触发点  
> **日期**：2026-09-05  
> **原则**：增强现有 SCOPE-019，不另起并行 Agent 通道。

---

## 0. 一览

| 优先级 | 数量 | 含义 |
|--------|------|------|
| **P0** | 必须做完才能宣称「按共识自动修好」 | 直连 DeepSeek、skip-permissions、成功=健康复检 PASS、SOP/记忆注入、目录锁、备份/diff/回滚骨架 |
| **P1** | 修好率与可运维紧随其后 | 事件流+薄前端、超时/轮次调参、卡死工单补扫、模型窗口告警处理 |
| **P2** | 增强与收口 | 脚本文件锁、RISK/EXCEPTION 策略收窄、stream-json 解析、Key 迁环境变量 |

| 现状可用性 | 说明 |
|------------|------|
| **可复用骨架** | 建单/复用、店铺冷却预算、FAIL 事件触发、后台收尾线程、`TICKET_RESULT` 解析、飞书、关 CDP、并发信号量雏形 |
| **与共识冲突/缺失** | 成功标准、CLI 启动参数与 env、持锁、手册记忆、过程可视化、落盘治理 |

---

## 1. 已具备（Keep）

| # | 能力 | 位置 | 备注 |
|---|------|------|------|
| K1 | 修复收尾触发 `trigger_auto_repair` | `health_task_service`（SUCCESS 后不触发；FAIL/RISK/EXCEPTION 会触发） | **事件主路径已有** |
| K2 | 独立 Session 建单/复用 | `AutoRepairTicketService.create_or_reuse` | 不污染主修复事务 |
| K3 | 店铺维冷却 + 日预算 | `evaluate_dispatch` / `mark_dispatched` / `AutoRepairShopState` | 防刷 token |
| K4 | 后台 `Popen` + 超时 `taskkill /T` | `AgentRepairDispatcher.dispatch` / `_wait_process` | 不阻塞请求线程 |
| K5 | 日志落盘 + 行锚 `TICKET_RESULT` | `_prepare_log_file` / `_parse_result` | 解析策略可保留，结论语义要改 |
| K6 | NEED_HUMAN/FAILED → 飞书 + 关 CDP | `_notify_need_human` / `_shutdown_browser` | 人机即停策略可保留 |
| K7 | 工单 API 列表/详情 | `/api/auto-repair-tickets` | 前端仍缺 |
| K8 | 全局并发信号量 | `_max_concurrent = 2` | **粒度不对**（见 G-LOCK），但「有上限」可演进 |
| K9 | Windows `.cmd` 经 `cmd /c` | `_build_command` | 与探活「用 claude.cmd」同向 |

---

## 2. P0 差距（阻塞「自动修好」）

### G-CLI-ENV — DeepSeek 直连与隔离配置

| | |
|--|--|
| **共识/探活** | 子进程：`ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`，Token，model=`deepseek-v4-flash-vision-exp`；**清代理**；隔离 config（用户 settings 含 **7897**） |
| **现状** | `Popen` **不传 env**；继承服务进程环境 + 用户 `~/.claude/settings.json`（含代理） |
| **改法** | 构造干净 `env`：注入 DeepSeek 变量；删除 `HTTP(S)_PROXY`/`ALL_PROXY`；`CLAUDE_CONFIG_DIR` 指向 runtime 下每工单或共享「无代理」settings；Token 从 settings 或 `DEEPSEEK_API_KEY` 读取（不写 git） |
| **验收** | 工单子进程抓包/日志确认直连 `api.deepseek.com`；无 7897 |

### G-CLI-FLAGS — 无人值守权限与调用形态

| | |
|--|--|
| **探活** | 无 flag → Read/Write 被拦；需 **`--dangerously-skip-permissions`**；用 **`claude.cmd`** |
| **现状** | `_build_command` 仅 `-p` + `--max-turns`，**无 skip-permissions** |
| **改法** | `claude.cmd --dangerously-skip-permissions -p ... --output-format text`（或 stream-json 见 P1）；`which` 优先 `.cmd`；工作目录尽量收窄到项目/artifacts |
| **验收** | 无人工点批准即可改测试文件、读截图 |

### G-SUCCESS — 成功标准 = 健康复检 PASS

| | |
|--|--|
| **共识** | 仅健康检测 **复检 PASS** 可 SOLVED |
| **现状** | Agent 自报 `TICKET_RESULT: SOLVED` 即入库 SOLVED；prompt 要求 `python script --skip-db` 通过即可 |
| **改法** | 收尾：解析 agent 输出后 **平台强制** `HealthTaskService` 对 `health_task_code` 再 `check`；PASS 才 `record_result(SOLVED)`；否则回滚脚本改动并 NEED_HUMAN/FAILED 或允许有限重试 |
| **验收** | 假 SOLVED（未复检）不能关单为 SOLVED |

### G-PROMPT-SOP-MEM — 手册 + 记忆 + 本单包

| | |
|--|--|
| **共识** | 强制 SOP + 相关 memory 片段 + 实例包 |
| **现状** | 内联短 prompt；无读 `docs/agent/SOP-操作手册.md` / `memory/`；实例字段不全（无 profile 路径、artifacts、FAIL 日志尾、diff 目录约定） |
| **改法** | `_build_prompt` 拼接：SOP 全文或路径强制 Read；`memory/项目运转.md` + 匹配 script/shop 片段；实例包结构化（ticket、paths、cdp、log tail、backup_dir） |
| **验收** | 日志/事件可见「已加载 SOP/记忆」；agent 行为符合红线表述 |

### G-LOCK-PROFILE — Agent 期间持有目录锁

| | |
|--|--|
| **共识** | 按 Profile **目录锁** 并发；Agent 全程持锁 |
| **现状** | 修复收尾 **先解锁 Profile** 再 `trigger_auto_repair`；旧 Spec 亦写 agent 不重新加锁；全局 semaphore=2 与目录无关 |
| **改法** | dispatch 前对 `repair_directory`/`profile` **重新加锁**（owner=`auto-repair:{ticket_code}`）；`_reap` finally 释放；并发改为「同 profile 互斥，跨 profile 并行」，可保留全局上限作安全阀 |
| **验收** | Agent RUNNING 时同 profile 调试/修复被拒；结束后锁释放 |

### G-SCRIPT-GOV — 落盘备份 / diff / 复检失败回滚

| | |
|--|--|
| **共识** | 允许改 `runtime/scripts`；改前备份；前端要 diff；复检未 PASS **默认回滚** |
| **现状** | prompt 甚至强调少改；无备份目录、无 diff 采集、无回滚 |
| **改法** | 唤起前快照相关脚本 → `artifacts/<ticket>/scripts_backup/`；收尾 `git diff` 或文件对比写入 events；SOLVED 前若复检 FAIL → restore backup |
| **验收** | 有 backup+diff 文件；复检失败后脚本内容恢复 |

### G-TIMEOUT-BUDGET — 轮次与时长过紧

| | |
|--|--|
| **现状** | `max_turns=4`，`max_seconds=120` |
| **现实** | 看图+改脚本+重跑+复检远超 4 轮/2 分钟 |
| **改法** | 配置化（env/settings）：例如 turns 20–40、seconds 600–1800；与店铺日预算区分 |
| **验收** | 一次真实 FAIL 排障不因默认 120s 误杀 |

---

## 3. P1 差距（修好率与可观测）

### G-EVENTS-FE — 思考/操作/diff 事件流 + 薄前端

| | |
|--|--|
| **共识** | 前端时间线：think / tool / screenshot / script_diff / recheck；内网全文脱敏 |
| **现状** | 单文件 stdout 日志；API 仅工单列表/详情；**无** `agent_events` 表/字段；无页面 |
| **改法** | 短期：收尾解析 log 切段写入 ticket.diagnosis 扩展或 JSON 列；中期：`agent_event` 表 + 轮询 API；前端 `/auto-repair-tickets` |
| **验收** | 一次探活工单可在 UI 看到步骤与 diff |

### G-SCAN-STUCK — 定时补漏未结/卡死工单

| | |
|--|--|
| **共识** | 辅路径：扫 PENDING 过久 / RUNNING 超时 |
| **现状** | `HealthTaskScheduler` **无** auto-repair 补扫；仅事件触发 |
| **改法** | scheduler 每 N 分钟：RUNNING 超时强杀+FAILED；PENDING 且可 dispatch 的再唤起 |
| **验收** | 人为卡住的 RUNNING 会被收口 |

### G-MODEL-WARN — unrecognized_model

| | |
|--|--|
| **探活** | CLI 警告 vision-exp 不在内建目录 |
| **改法** | env `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1` 和/或 settings `modelOverrides`/`behavesAs` |
| **验收** | stderr 无阻断；长上下文不被错误 200k 截断误伤（按需） |

### G-CDP-TOOLING — `.claude/tools/cdp_inspector.py`

| | |
|--|--|
| **现状** | prompt 依赖 `python .claude/tools/cdp_inspector.py`；仓库 **`.gitignore` 含 `.claude/`**，生产机未必有该工具 |
| **改法** | 工具迁入 `tools/cdp_inspector.py` 或 `backend` 可分发路径并进 git；prompt 改绝对/稳定相对路径；截图写入 `runtime/artifacts/<ticket>/` |
| **验收** | 干净 clone 的机器上 agent 能截图 |

### G-TRIGGER-SCOPE — FAIL vs RISK/EXCEPTION

| | |
|--|--|
| **曾讨论选项** | A 仅 FAIL；B 维持现状；C FAIL+EXCEPTION、RISK 不拉 CLI |
| **已锁定（2026-09-05）** | **B：维持现状** |
| **行为** | **FAIL** → 全量排障（可改脚本 + 目标复检 PASS）；**EXCEPTION** → 同全量排障；**RISK** → **仍唤起 CLI**，但 prompt 约束为 **只诊断判级**，不改脚本、不过验、结论偏 NEED_HUMAN |
| **代码** | `health_task_service` 在 `status in (FAIL, RISK)` 与异常路径 `EXCEPTION` 均 `trigger_auto_repair`；dispatcher RISK 分支 steps 已区分——**保留，不收窄触发面** |
| **实现注意** | 成功标准仍以健康复检 PASS 为准时：**RISK 工单不应走「改脚本 + 复检 PASS → SOLVED」主路径**；RISK 收尾以诊断 + NEED_HUMAN/FAILED 为主，避免与「仅诊断」SOP 冲突 |
| **验收** | FAIL/EXCEPTION 可 SOLVED（复检 PASS）；RISK 唤起后不落盘改脚本、不宣称业务已修好 |

---

## 4. 触发策略锁定（选项 B · 2026-09-05）

**已拍板：B。** 不收窄触发面。

| issue_type | 唤起 CLI | 行为 |
|------------|----------|------|
| FAIL | 是 | 全量排障；SOLVED ⇔ 健康复检 PASS |
| EXCEPTION | 是 | 同 FAIL |
| RISK | 是 | **仅诊断**；不改脚本、不过验；终态偏 NEED_HUMAN，**不**走复检 PASS→SOLVED 主路径 |

Slice E 仅文档/测试对齐，不删 RISK/EXCEPTION 触发代码。

---

## 5. P2 差距（收口）

| ID | 项 | 说明 |
|----|----|------|
| G-FILE-LOCK | 脚本文件锁 | 跨店并行改同一 `.py` 时互斥 |
| G-KEY-ENV | Key 迁 `DEEPSEEK_API_KEY` | 减少读 settings；文档化运维 |
| G-STREAM | `--output-format stream-json` | 更易拆 think/tool 事件 |
| G-CONCUR-TUNE | 全局上限 vs 目录锁 | semaphore 改为「按 profile 锁 + 全局 max」 |
| G-SPEC-SYNC | 回写 Product-Spec FLOW-007 | 持锁、复检 PASS、CLI 参数与探活一致 |

---

## 6. 建议实现切片（顺序）

```text
Slice A（能拉起来且直连）✅ 2026-09-05 代码已落地
  G-CLI-ENV + G-CLI-FLAGS + G-MODEL-WARN + G-TIMEOUT-BUDGET
  → dispatcher：DeepSeek 直连 env、清代理、隔离 CLAUDE_CONFIG_DIR、
    `--dangerously-skip-permissions`、默认 30 轮 / 900s；单测 14 passed
  → Windows 真实 FAIL 冒烟仍待做（内部机）

Slice B（成功定义正确）✅ 2026-09-05 代码已落地
  G-SUCCESS + G-PROMPT-SOP-MEM + G-CDP-TOOLING
  → FAIL/EXCEPTION：agent SOLVED 后平台 `execute_check(..., follow_up=False)`，PASS 才关单
  → RISK：禁止 SOLVED（自报 SOLVED 也收成 NEED_HUMAN）
  → prompt 注入 SOP + memory + 实例包；CDP 工具 `tools/cdp_inspector.py`
  → 单测 23 passed；Windows 真实复检冒烟仍待做

Slice C（安全并发与落盘）✅ 2026-09-05 代码已落地
  G-LOCK-PROFILE + G-SCRIPT-GOV
  → FAIL/RISK/EXCEPTION 收尾不先放 Profile 锁；dispatcher 以 auto-repair:{ticket} 接管
  → _reap finally unlock_if_owner；同 profile 互斥（steal 仅 run:{本次}）
  → FAIL/EXCEPTION 唤起前备份 runtime/scripts；收尾写 script.diff；非 SOLVED 默认回滚
  → RISK 不备份、不回滚（默认不写脚本）
  → 单测 test_auto_repair_slice_c.py 全绿

Slice D（可观测）✅ 2026-09-05 代码已落地
  G-EVENTS-FE + G-SCAN-STUCK
  → 日志/产物组装 think/tool/screenshot/script_diff/recheck；详情 API 带 events+diff
  → 薄前端 `/auto-repair-tickets`（RUNNING 轮询）
  → 调度每分钟补扫：RUNNING 超时 FAILED+杀 pid；过久 PENDING 再唤起
  → 单测 test_auto_repair_slice_d.py 全绿

Slice E（策略已定 B）✅ 2026-09-05 代码/文档已落地
  测试覆盖 FAIL/EXCEPTION/RISK 三分支 + P2 收口（G-SPEC-SYNC）
  → FLOW-007/REQ-011/§11 与实现一致
  → P2 其余（文件锁/stream-json/Key 迁 env/semaphore 调参）明确推迟
```

---

## 7. 非目标（本清单不展开）

- 另建网关 Agent 替代 Claude Code  
- 自动过滑块/验证码  
- 采集任务失败接入  
- 多 Agent 协作  
- 将触发面收窄为「仅 FAIL」（已否决，选 B）

---

## 8. 相关文件

| 文件 | 角色 |
|------|------|
| `backend/app/services/agent_repair_dispatcher.py` | 主改造面 |
| `backend/app/services/auto_repair_ticket_service.py` | 锁记账/事件字段可能扩展 |
| `backend/app/services/health_task_service.py` | 触发时机、释锁顺序、复检调用 |
| `backend/app/api/routes/auto_repair_tickets.py` | 事件 API |
| `frontend/...` | 薄工单页（尚无） |
| `docs/agent/*` | SOP/记忆/本清单 |
