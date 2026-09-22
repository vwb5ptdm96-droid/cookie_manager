# Agent 文档索引

本目录定义 **Session 维护系统 · Agent 维护层** 的产品共识与 Agent 上岗材料。

| 文档 | 说明 |
|------|------|
| [AGENT-MAINTENANCE-LAYER.md](./AGENT-MAINTENANCE-LAYER.md) | **共识基线（LOCKED）**：排障红线 + 2026-09-20 站点值班增量 |
| [ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md](./ENHANCEMENT-PATH-CLAUDE-CLI-DEEPSEEK.md) | **增强路径（LOCKED）**：Claude Code CLI + `deepseek-v4-flash-vision-exp`，直连 DeepSeek、不走代理 |
| [GAP-ANALYSIS-DISPATCHER.md](./GAP-ANALYSIS-DISPATCHER.md) | **改造差距清单**：现有 dispatcher vs 共识/探活（P0–P2 + 切片顺序） |
| [SOP-操作手册.md](./SOP-操作手册.md) | Repairer **强制**排障手册 |
| [SOP-值班手册.md](./SOP-值班手册.md) | Watcher / Collector / SRE 值班手册 |
| [SITE-OPERATOR-MATRIX.md](./SITE-OPERATOR-MATRIX.md) | **已拍板**：角色 × 页面 × 工具 × 成功证据 |
| [SITE-OPERATOR-UX.md](./SITE-OPERATOR-UX.md) | **已拍板**：值班台 UX 契约（不整站换皮） |
| [memory/](./memory/) | 项目记忆落点与模板 |

实现代码仍主要在 `backend/app/services/agent_repair_dispatcher.py` 等。
