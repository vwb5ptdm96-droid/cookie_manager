# Agent 维护层 · 共识基线（LOCKED）

> **状态**：产品/技术对齐已锁定。2026-09-20 追加「站点值班」增量（采集另立工单、早报只工作台、无单对话等进程内 loop、重启后端可进工具但须确认）。排障红线不放宽。  
> **日期**：2026-09-05 锁定排障层；2026-09-20 锁定值班增量  
> **关系**：增强并产品化既有 SCOPE-019 自动排障；SCOPE-020 收窄为「过程可视化调试台」优先服务修好率；值班面见 §12 与 [SITE-OPERATOR-MATRIX.md](./SITE-OPERATOR-MATRIX.md)。  
> **非目标**：本文不选定具体模型供应商或网关实现。

---

## 1. 问题与目标

**痛点**：Playwright 维护脚本不稳定 → 修复失败 → cookie 未及时恢复 → 下游采集中断。

**目标**：在修复脚本 **FAIL** 后，由 Agent 在真实浏览器（CDP）与 `runtime/` 脚本上下文中排障，**把登录态修到可用**。

**成功定义（硬）**：

```text
仅当绑定的健康检测任务复检结果 = PASS 时，才可标记 SOLVED / 自动修好。
```

页面“看起来登录”、Agent 自述成功、仅脚本 `--skip-db` 跑通 → **一律不算成功**。

---

## 2. 已锁定决策一览

| # | 维度 | 决策 |
|---|------|------|
| 1 | 成功标准 | 健康检测 **复检 PASS**，cookie/登录态真实可用 |
| 2 | 脚本权限 | **允许修改** `runtime/scripts` 下相关脚本并 **落盘** |
| 3 | 触发业务条件 | **FAIL / EXCEPTION：全量排障**；**RISK：仍唤起 CLI，仅诊断判级**（选项 B，2026-09-05 锁定）。主事件仍来自修复脚本收尾，不含采集任务失败 |
| 4 | 接入形态 | **主：修复收尾事件立即拉起**（FAIL/EXCEPTION/RISK 见上）；**辅：定时扫描未结/卡死工单补漏** |
| 5 | 并发 | **按 Profile 目录加锁并发**；同目录串行；跨目录可并行 |
| 6 | 人机验证 | **识别即停 + 飞书**；不自动过滑块/短信/扫码/设备验证 |
| 7 | 优先级 | **先提高自动修好率**；过程可视化与接入同迭代（薄前端） |
| 8 | 架构关系 | **增强现有自动排障路径**；网关/模型形态另议 |
| 9 | Agent 上下文 | 必须注入 **操作手册 + 项目记忆 + 本单实例包** |
| 10 | 前端过程 | 展示 **思考 + 操作** 时间线；**内网可看全文** |
| 11 | Diff | 前端 **必须展示** 脚本改动 diff |

---

## 3. 端到端主路径

```text
修复脚本 ScriptRun 终态 = FAIL
  → 创建/复用自动排障工单（PENDING）
  → 组装上下文：
       操作手册（docs/agent/SOP-操作手册.md）
     + 项目记忆（docs/agent/memory/** 相关片段）
     + 本单实例包（ticket、script 路径、profile、cdp、FAIL 日志、artifacts）
  → 获取 Profile 目录锁
  → 拉起 Agent（主：事件；辅：定时补扫未结/卡死）
  → 循环：思考 → 工具操作（CDP / 改脚本落盘 / 重跑修复）
       每步 append 事件流（供前端）
  → 跑绑定健康检测复检
  → PASS ⇒ SOLVED（可写记忆摘要）
  → 人机/超时/预算/搞不定 ⇒ NEED_HUMAN + 飞书
  → 释放目录锁；保留 diff/备份/事件可回放
```

**辅路径（定时）**只做：

- 未结工单（PENDING 过久、RUNNING 卡死）回收/续跑  
- **不**作为“扫全库历史 FAIL”的业务主入口  

---

## 4. 上下文三件套

### 4.1 操作手册（SOP）

| 项 | 约定 |
|----|------|
| 落点 | `docs/agent/SOP-操作手册.md` |
| 性质 | 版本化、进 git，Agent **强制加载** |
| 内容 | 触发条件、成功标准、工具边界、落盘与回滚、人机红线、结论回写格式 |

### 4.2 项目记忆（Memory）

| 项 | 约定 |
|----|------|
| 落点 | `docs/agent/memory/`（见该目录 README） |
| 性质 | 可演进；按「全局运转 / 脚本 / 店铺」分片；**脱敏** |
| 加载 | 按本单 channel/shop/script **检索挂载相关片段**，禁止无差别倾倒整库 |
| 回写 | SOLVED 后可追加「有效修复模式」短记（仍脱敏） |

### 4.3 本单实例包（Runtime ticket pack）

由调度器/dispatcher 生成，至少包括：

- `ticket_id`、issue 类型、关联 `health_task_code`、`script_run_id`  
- 脚本绝对/相对路径、`profile_key`、user-data 路径、`cdp_port`  
- FAIL 日志尾部、artifacts 目录、最近检测配置摘要（URL/规则，无 cookie 明文）  

---

## 5. 锁与并发

| 锁 | 粒度 | 规则 |
|----|------|------|
| Profile 目录锁 | 单个 profile / user-data-dir | Agent 全流程持有；同目录禁止第二修复/Agent/调试抢占 |
| 脚本文件锁（实现时） | 单个 script 文件路径 | 跨店并行时若改**同一脚本文件**必须互斥或排队 |
| 全局 repair 大锁 | — | 产品决策为目录级并发；实现阶段应弱化/取消与本决策冲突的全局串行 |

> 注：旧 FLOW-007 中「修复收尾已释锁后 Agent 不重新加目录锁」与本共识冲突时，**以本文为准**：Agent 工作期间必须持目录锁。

---

## 6. 脚本落盘与 diff

1. 改前：对目标文件做备份（建议 `runtime/artifacts/<ticket>/scripts_backup/`）  
2. 改中：仅限本单相关维护脚本；禁止改 `backend/app/core`、迁移、`.env`  
3. 改后：生成 unified diff，写入事件流 + artifacts，**前端必显**  
4. 复检未 PASS：默认 **回滚** 本单脚本改动（除非人工指定保留）——实现时作为硬规则写入 SOP  

---

## 7. 前端（薄 SCOPE-020 · 联调优先）

**路由建议**：`/auto-repair-tickets`（名称可调整）

| 区块 | 要求 |
|------|------|
| 工单列表/详情 | 状态、店、脚本、profile、触发 run、时间 |
| 时间线 | 拉起 → 读手册/记忆 → CDP → 操作 → 改脚本 → 重跑 → 复检 → 终态 |
| 思考流 | Agent 推理文本；**内网可看全文**（仍做 cookie/密码等自动脱敏） |
| 操作流 | 工具名、参数摘要、结果摘要、截图链接 |
| Diff | 每个落盘文件的 unified diff，可展开 |
| 复检 | 展示复检请求摘要与 PASS/FAIL |

数据面建议：工单 + `agent_events`（或等价 JSON 流水）轮询；SSE 后置。

---

## 8. 与 SCOPE-019 的关系

| 保留 | 调整/增强 |
|------|-----------|
| 自动排障工单模型、冷却/预算骨架 | 成功标准改为 **健康复检 PASS** |
| FAIL 触发主路径 | 明确辅路径定时补漏 |
| 人机不停过验证 | 目录锁策略按本文 |
| Claude CLI 可为默认实现之一 | **接入形态可插拔**（网关等）另议，不写死本文 |
| 无前端 | 补薄前端过程可视化 |

---

## 9. 明确不做（排障工人范围）

- 检测 FAIL 但未执行修复时自动开 **Repairer**
- 自动完成人机验证
- 多 Agent 协作编排
- 无 diff、无复检的“静默改脚本”
- 把模型供应商锁定为唯一实现（待增强路径讨论）
- 用现有 Claude CLI 外包做全站无单问答
- Collector 使用 CDP / 改维护脚本 / 擅自写映射

> 2026-09-20：**采集任务失败改为另立 `cookie_sync` 工单**（Collector），不再属于「Agent 完全不管」。仍禁止把它交给 Repairer 或套用健康复检 PASS。

---

## 10. 文档与代码索引

| 路径 | 用途 |
|------|------|
| `docs/agent/AGENT-MAINTENANCE-LAYER.md` | 本文：共识基线 |
| `docs/agent/SOP-操作手册.md` | Repairer 强制 SOP |
| `docs/agent/SOP-值班手册.md` | Watcher / Collector / SRE SOP |
| `docs/agent/SITE-OPERATOR-MATRIX.md` | 角色 × 页面 × 工具 × 成功证据（2026-09-20 拍板） |
| `docs/agent/SITE-OPERATOR-UX.md` | 值班台 UX 契约（2026-09-20） |
| `docs/agent/memory/` | 项目记忆分片 |
| `docs/Product-Spec.md` SCOPE-019/020 | 规格真源（实现前可再增补 SCOPE 条目） |
| `backend/.../agent_repair_dispatcher.py` | 现有拉起实现（待增强） |

---

## 11. 下一讨论口

增强路径已锁定，见 [ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md](./ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md)。  
实现顺序见矩阵 §7：S0 unwrap / S2 早报 / S3 loop / S4 采集工单 / **S5 SRE 闸已落地**。
CLI 兼容层：`AUTO_REPAIR_USE_CLI=1`。

---

## 12. 站点值班增量（2026-09-20 LOCKED）

详细矩阵：[SITE-OPERATOR-MATRIX.md](./SITE-OPERATOR-MATRIX.md)。值班 SOP：[SOP-值班手册.md](./SOP-值班手册.md)。

一个 harness、五套职责（Dispatcher 为平台代码，其余为 Agent 角色）：

| 角色 | 成功证据 | 写权限要点 |
|------|----------|------------|
| Watcher | 早报/问答数字可对页面 | 无。早报只工作台、不飞书。无单问答等 S3 进程内 loop |
| Dispatcher | 工单状态机合法 | 建排障单 + 建 `cookie_sync` 单；不改脚本 |
| Repairer | 绑定健康检测复检 PASS | 本单脚本 + 本单 CDP；RISK 诊断-only。红线见本文 §1–§8 |
| Collector | 采集任务复检 PASS | 可重派补采；无映射 NEED_HUMAN；无 CDP、无改脚本、无写映射 |
| SRE | 诊断可核验；重启后 health 探活 | 重启后端 / 回收停滞 **可进工具，必须工作台确认** |

采集失败与健康修复失败 **分单、分成功定义、分工具箱**。OUT-010 不变：健康任务仍不自动联动采集任务。
