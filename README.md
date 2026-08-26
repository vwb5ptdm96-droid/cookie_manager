# cookie_manager — 管理 cookie 平台

# Windows 原生 Session 维护任务系统

内部运维工作台，用于管理会话维护任务、健康检查、脚本库、Profile、人工修复工单、环境自检和运行日志。

## 目录结构

```text
session-maintenance-system/
├── backend/                 # FastAPI 后端 + Alembic
├── frontend/                # Vue 3 + Vite 前端
├── runtime/                 # 运行时目录，保存脚本、Profile、日志、产物
├── .env.example             # 环境变量示例
└── start_backend.bat        # Windows 后端启动脚本
```

## 环境要求

- Windows 10 / Windows Server，人工修复链路需要桌面会话或 RDP。
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

- 人工修复浏览器依赖 Windows 桌面会话，不支持纯无头后台修复。
- 代码当前没有登录鉴权与权限体系。
- `legacy cookie` 外部表不是本仓库创建和维护的，它只在健康检查链路里被读取。
