# cookie_manager — 管理 cookie 平台

# Windows 原生 Session 维护任务系统

内部运维工作台，用于管理会话健康检测任务、脚本库、Profile 目录库、脚本运行、Cookie 扩展采集与一键上报、自动排障（Claude Code）、环境自检和运行日志。

> 说明：早期版本中的独立「维护任务」「旧健康检测」「人工修复工单」模块已废弃（Spec OUT-007/008），由健康检测任务统一取代；修复失败现走飞书提醒或自动排障闭环（SCOPE-019），不再生成人工工单。

## 目录结构

```text
session-maintenance-system/
├── backend/                 # FastAPI 后端 + Alembic
├── frontend/                # Vue 3 + Vite 前端
├── runtime/                 # 运行时目录，保存脚本、Profile、日志、产物
├── tools/watchdog.py        # 生产健康探针（计划任务 SessionBackend-Watchdog 调用）
├── .env.example             # 环境变量示例
├── run_server.py            # 生产启动入口（alembic 迁移 + uvicorn，轮转日志）
├── start_interactive.bat    # 生产启动脚本（计划任务调用，优先 backend\.venv）
├── start_backend.bat        # 开发启动脚本（前台运行）
├── restart_backend.bat      # 生产重启后端（杀 8081 + 计划任务 end/run）
└── start.vbs                # 双击拉起开发后端+前端（仅开发用）
```

## 环境要求

- Windows 10 / Windows Server；生产后端以计划任务运行在交互会话，自动排障 / 有头 Chrome 需登录桌面可见。
- Python 3.11。
- Node.js 20+。
- `pnpm`。

## 初始化

1. 复制 `.env.example` 为 `.env`。
2. 安装后端依赖：

```powershell
cd backend
python -m pip install -r requirements.txt
```

3. 安装前端依赖：

```powershell
cd ..\frontend
pnpm install
```

## 环境变量

当前代码真实读取的环境变量只有这些：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `APP_ENV` | 运行环境标识 | `dev` |
| `APP_NAME` | FastAPI 应用名 | `session-maintenance-system` |
| `APP_HOST` | 后端监听地址 | `0.0.0.0` |
| `APP_PORT` | 后端监听端口 | `8081` |
| `DEPLOY_ROOT` | 项目根目录 | 当前仓库根目录 |
| `RUNTIME_ROOT` | 运行时根目录 | `<项目根目录>\\runtime` |
| `DATABASE_URL` | 主业务数据库连接串 | 默认 SQLite，本地文件位于 `runtime/session_maintenance.db` |
| `CHROME_PATH` | 目录库「打开调试」使用的 Chrome 可执行文件路径 | 自动探测常见安装路径 |

说明：

- 默认配置会使用 SQLite，适合本地开发和联调。
- 如果要切换 MySQL，只需要把 `DATABASE_URL` 改成可用连接串，例如：

```env
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/session_maintenance?charset=utf8mb4
```

## 启动后端

推荐直接用根目录脚本：

```powershell
.\start_backend.bat
```

这个脚本会做三件事：

1. 读取 `.env`（端口、路径、Chrome 路径全部由 `.env` 驱动，路径不配走自动检测）。
2. 创建 `runtime` 下的关键目录、执行 `alembic upgrade head`。
3. 启动 `uvicorn app.main:app`，监听 `APP_PORT`。

**部署可移植**：`APP_HOST/APP_PORT/DEPLOY_ROOT/RUNTIME_ROOT/DATABASE_URL` 均来自 `.env`，按代码所在位置自动推导，不绑定盘符。生产环境前端 `dist` 由后端同端口托管，浏览器直接访问 `http://<服务器IP>:<APP_PORT>` 即可；默认端口被占时只改 `.env` 的 `APP_PORT`。

只验证迁移时可以执行：

```powershell
.\start_backend.bat --migrate-only
```

如果不想用批处理，也可以手动启动：

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --app-dir .
```

后端默认地址（端口以 `.env` 的 `APP_PORT` 为准）：

- API: `http://127.0.0.1:<APP_PORT>`
- 健康检查: `http://127.0.0.1:<APP_PORT>/api/health`

## 以计划任务运行后端（生产）

生产环境唯一入口是**计划任务**，在交互会话下运行（有头 Chrome 窗口可见）；不要在生产机器上手动起 uvicorn，以免与计划任务冲突（端口 8081）。

| 入口 | 用途 | 说明 |
|---|---|---|
| 计划任务 `SessionBackend-Interactive` | **生产唯一入口** | `cmd /c start_interactive.bat` → `run_server.py`（先 alembic 迁移再起 uvicorn），在交互会话运行 |
| `start_interactive.bat` | 生产启动脚本 | 被计划任务调用；优先 `backend\.venv\Scripts\python.exe`；日志由 `run_server.py` 写入 `runtime/logs/backend.log`（10MB×5 轮转） |
| `restart_backend.bat` | 生产重启脚本 | 杀 8081 监听进程 → `schtasks /end` 残留实例 → `/run` 重新拉起 |
| `tools/watchdog.py` | 生产健康探针 | 端口 / SQLite / RDS 探活 + 飞书告警（计划任务 `SessionBackend-Watchdog`） |

日常操作：

```bat
:: 启动
schtasks /run /tn SessionBackend-Interactive
:: 重启（先 /end 再 /run，见下方注意）
restart_backend.bat
:: 停止
schtasks /end /tn SessionBackend-Interactive
:: 查看 8081 监听状态
netstat -ano | findstr :8081
```

注意：

- 直接 `schtasks /run` 重启往往失败——若上次实例未被清理，调度器会提示"任务正在运行中"并拒绝新实例，**必须先 `/end` 再 `/run`**。
- 运行期间不要再用 `start_backend.bat` 或手工 `uvicorn` 起第二个实例，会撞 `APP_PORT`。
- `run_server.py` 的所有路径按脚本自身位置推导，不绑定盘符，部署到任何目录均可直接复用。
- 历史 NSSM 服务（`SessionBackend`）已停用，`tools/nssm/` 仅保留说明文件。

详细运维操作（启动 / 重启 / 停止 / 备份恢复 / 监控告警 / 安全基线）见 [docs/OPS-STARTUP.md](docs/OPS-STARTUP.md)、[docs/OPS-BACKUP.md](docs/OPS-BACKUP.md)、[docs/OPS-MONITORING.md](docs/OPS-MONITORING.md)、[docs/OPS-SECURITY.md](docs/OPS-SECURITY.md)。

## 启动前端

```powershell
cd frontend
pnpm dev
```

开发服务器启动后，按 Vite 输出地址访问即可。

## 常用验证命令

后端测试：

```powershell
cd backend
python -m pytest
```

后端编译检查：

```powershell
cd backend
python -m compileall app
```

前端构建：

```powershell
cd frontend
pnpm build
```

## 运行时目录

`runtime/` 下当前约定的关键目录：

- `runtime/profiles/`：浏览器 Profile
- `runtime/scripts/`：上传脚本
- `runtime/artifacts/`：任务和修复产物
- `runtime/logs/`：运行日志
- `runtime/cache/`：缓存文件

## 当前实现边界

- 自动排障（SCOPE-019）唤起本机 Claude Code 连接 CDP 有头 Chrome 现场排障，依赖交互会话，不支持纯无头后台排障。
- 代码当前没有登录鉴权与权限体系。
- `legacy cookie` 外部表不是本仓库创建和维护的：健康检测读取；扩展采集 / 手动一键上报按既有列先查后改写回（不新增、不修改旧表列结构）。
- 废弃模块（独立维护任务 / 旧健康检测 / 人工修复工单）已移出产品范围；对应后端残留路由见 `docs/DEV-PLAN.md` Phase 6 现状更新。
