# 增强路径：Claude Code CLI × DeepSeek Vision（LOCKED）

> **日期**：2026-09-05  
> **上级文档**：[AGENT-MAINTENANCE-LAYER.md](./AGENT-MAINTENANCE-LAYER.md)  
> **状态**：接入形态已拍板；实现与 Windows 探活待做。

---

## 1. 决策摘要

| 项 | 锁定值 |
|----|--------|
| Agent 运行时 | **Claude Code CLI**（`claude`） |
| 模型供应商 | **DeepSeek** |
| 主模型 | **`deepseek-v4-flash-vision-exp`**（多模态看图，非 video） |
| 文本兜底 | `deepseek-v4-flash`（Vision 不可用或纯文本小任务） |
| API 形态 | DeepSeek **Anthropic 兼容端** `https://api.deepseek.com/anthropic` |
| 鉴权 | `ANTHROPIC_AUTH_TOKEN` = DeepSeek API Key（Windows 机已具备） |
| 网络 | **直连 `api.deepseek.com`，不走本地 HTTP 代理** |
| 拉起方式 | 修复脚本 FAIL 事件为主；定时补未结/卡死工单为辅 |
| 成功标准 | 健康检测 **复检 PASS**（不变） |

---

## 2. 为什么这样选

- CLI 提供现成工具循环（读改 `runtime/scripts`、跑命令、看产物），贴合「允许落盘改脚本」。  
- Vision-Exp 可消费 **CDP 截图**，服务弹窗/遮罩/风控形态判断。  
- 官方支持 Claude Code → DeepSeek `/anthropic`，无需自研完整 agent 框架。  
- 机房/Windows 节点 **Key 已有且直连稳定**，减少网关与代理变量。

---

## 3. 进程级环境变量（每工单子进程注入）

**禁止**写入仓库、`.env` 提交物或全局强制覆盖开发者日常 Claude 配置。  
仅由 `agent_repair_dispatcher`（或包装脚本）在子进程环境设置：

```bat
set ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
set ANTHROPIC_AUTH_TOKEN=%DEEPSEEK_API_KEY%
set ANTHROPIC_MODEL=deepseek-v4-flash-vision-exp
set ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-flash-vision-exp
set ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-flash-vision-exp
set ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
set CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash-vision-exp
```

可选（联调后再定是否默认开启）：

```bat
set CLAUDE_CODE_EFFORT_LEVEL=max
```

### 代理隔离（硬要求）

子进程启动时 **清除** 可能劫持 HTTPS 的代理变量，确保直连 DeepSeek：

```text
HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / http_proxy / https_proxy / all_proxy
```

（以及企业环境若注入的 `NO_PROXY` 误伤，需保证 `api.deepseek.com` 直连。）

Key 来源建议：Windows 用户/机器环境变量 `DEEPSEEK_API_KEY`，或仅管理员可读的本地密钥文件；**不要**进 git。

---

## 4. 运行时数据流

```text
ScriptRun FAIL
  → 工单 + Profile 目录锁
  → 组装：SOP + memory 片段 + 本单 pack
  → 子进程 env（上文）+ 无代理
  → claude CLI（非交互 / -p 或项目约定 headless 参数）
       ├─ 读 FAIL 日志、脚本、记忆
       ├─ CDP 截图 → artifacts → 模型看图（Vision）
       ├─ 改脚本落盘 + diff 事件
       └─ TICKET_RESULT 行
  → 平台执行健康复检
  → PASS ⇒ SOLVED；否则回滚脚本改动 / NEED_HUMAN
  → 事件流 → 前端（思考全文脱敏 + 操作 + diff + 截图）
```

---

## 5. 多模态约定

| 输入 | 约定 |
|------|------|
| 主视觉输入 | CDP **截图文件**（PNG/JPEG）写入本单 artifacts |
| 不主用 | 视频 mp4 作为模型输入 |
| 必须验证 | CLI 路径下 Read/附带图片时，请求是否真正带 image 到 Vision-Exp |
| 风控 | 截图识别滑块/短信/扫码等 → 立即 NEED_HUMAN，不自动过验 |

---

## 6. Windows 探活清单（实现前必做）

在排障机（`SD-20251221BCDN` 或当前生产节点）**无代理**环境：

1. `claude --version` 可用  
2. 仅子进程 env 指向 DeepSeek，执行：`claude -p "只回复 pong"`  
3. 给定本地弹窗截图，要求读出按钮文案（确认 **Vision** 生效）  
4. 在临时目录让 CLI 做无害文件编辑并产出 diff  
5. 确认出站为 `api.deepseek.com`，model 为 `deepseek-v4-flash-vision-exp`  
6. 确认系统代理变量未作用于该子进程  

探活失败则不进入自动 FAIL 拉起。

### 6.1 探活实绩（2026-09-05 · SD-20251221BCDN）

| 项 | 结果 |
|----|------|
| Claude Code | **2.1.259**（`claude.cmd`；PowerShell 下 `claude.ps1` 受 ExecutionPolicy 限制，自动化请用 `.cmd`） |
| Key 位置 | **不在** Process/User/Machine 的 `DEEPSEEK_API_KEY`；在 `%USERPROFILE%\.claude\settings.json` → `env.ANTHROPIC_AUTH_TOKEN` |
| 用户 settings 现状 | `model=deepseek-v4-flash-vision-exp`；**同时写了** `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`（与「Agent 直连」冲突，工单子进程必须覆盖/清除） |
| 直连 DeepSeek | `https://api.deepseek.com` 可达（无 key → 401；有 key → models/chat 正常） |
| models 列表 | 含 `deepseek-v4-flash-vision-exp` / `deepseek-v4-flash` / `deepseek-v4-pro` |
| 直连文本 | `deepseek-v4-flash` chat → **`pong`** |
| 直连 Vision（OpenAI + Anthropic 兼容） | 看本地 PNG → 读出 `CONFIRM_BUTTON_O`（测试图为 `CONFIRM_BUTTON_OK`，末字母被裁切属测图问题；**Vision 通路成立**） |
| CLI 文本 `-p` | **`pong` 成功**（隔离 config、无代理） |
| CLI 无 skip-permissions | Read/Write **被权限门挡住**（不可无人值守） |
| CLI + `--dangerously-skip-permissions` | 改文件 **`AFTER_EDIT_OK` 成功**；Read 截图 **成功返回文案** |
| 告警 | `unrecognized_model`：当前 CLI 目录未内建该 model id；可设 `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1`，或按 CLI 提示做 `modelOverrides`/`behavesAs` |

**自动化拉起最低命令形态（示意）**：

```bat
claude.cmd --dangerously-skip-permissions -p "<prompt>" --output-format text
```

并配合：隔离 `CLAUDE_CONFIG_DIR`（无 7897）、注入 DeepSeek env、清代理。

产物日志目录：`D:\session-maintenance-system\runtime\artifacts\_agent_probe\`（含 `probe_log2.txt` / `probe_log3.txt`）。

---

## 7. 与现有代码关系

| 现有 | 增强点 |
|------|--------|
| `agent_repair_dispatcher.py` | 注入 DeepSeek env、清代理、模型 id、日志/事件捕获 |
| SCOPE-019 工单 | 成功标准对齐「健康复检 PASS」；事件流供前端 |
| 全局 Claude 配置 | **不改**；仅工单子进程 |

---

## 8. 明确不做（本路径）

- 强制走 `127.0.0.1:789x` 等本地代理访问 DeepSeek  
- 把 DeepSeek Key 写入 git / 前端  
- 用纯文本 Flash 冒充已具备看图能力（仅作兜底）  
- 以模型自述代替健康复检 PASS  

---

## 9. 修订

变更主模型 id 或 Base URL 时，更新本文 + CHANGELOG，并重新跑 §6 探活。
