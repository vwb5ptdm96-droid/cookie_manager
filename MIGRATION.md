# 迁移部署清单

## 前提规范

所有路径强制使用相对于 `DEPLOY_ROOT`（项目根目录）的相对路径，**不允许绝对路径**。

- 脚本目录 → `runtime/scripts/uploaded/<name>/<version>/`
- Chrome 用户数据目录 → `runtime/profiles/<profile_name>/`
- 执行产物 → `runtime/artifacts/runs/<run_id>/`

以此保证迁移时只需复制整个项目文件夹，无需处理外部路径。

## 前置准备（新机器）

- [ ] Python 3.12+ 安装（已测试 3.14）
- [ ] Google Chrome 安装（CDP 脚本需要）
- [ ] 能访问阿里云 RDS（MySQL）— 检查网络连通性

## 步骤

### 1. 复制项目文件

将整个 `session-maintenance-system` 目录复制到新机器。

### 2. 安装 Python 依赖

在 `backend/` 下建虚拟环境（`start_backend.bat` 会自动检测 `backend\.venv`）：

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 3. 安装 Playwright 浏览器内核

```bash
playwright install chromium
```

### 4. 重建 Chrome 用户数据目录

> 旧版 profile 注册了绝对路径（如 `D:\拼多多cookie目录\moren-chrome`），迁移后需清理。

```bash
# 删除旧的绝对路径 profile
# 在 runtime/profiles/ 下重建同名目录
mkdir -p runtime/profiles/moren-chrome
```

然后通过页面重新注册 profile，路径填相对路径：`profiles/moren-chrome`。

### 5. 配置环境变量

复制 `.env.example` 为 `.env`（`.env` 不进 git，每台机器单独配）。**路径项不需要配**，代码自动检测项目根目录；只需按实际环境填外部依赖：

- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` — RDS 可达即可
- `TXY_ACCOUNT` / `TXY_PASSWORD` — 天巡云登录凭证
- `FEISHU_WEBHOOK_URL` — 飞书机器人通知地址

> `DEPLOY_ROOT` / `RUNTIME_ROOT` / `DATABASE_URL` 均可不配：默认分别指向项目根目录、`runtime/`、`runtime/session_maintenance.db`。如需自定义，写**相对项目根目录**的相对路径即可，例如 `RUNTIME_ROOT=runtime`。

### 6. 防火墙放行端口

端口以 `.env` 的 `APP_PORT` 为准（默认 8081），放行该端口：

```bash
netsh advfirewall firewall add rule name="Session Maintenance 8081" dir=in protocol=tcp localport=8081 action=allow
```

### 7. 启动服务

推荐直接用根目录脚本（自动检测 `backend\.venv` 并先跑迁移）：

```bash
.\start_backend.bat
```

手动启动：

```bash
cd backend
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8081
```

### 8. 验证

- 浏览器访问 `http://<新机器IP>:8399` — 前端页面正常
- 切换到"健康检测"页面，点击"执行修复" — 脚本在本机子进程执行

## 目录结构说明

```
session-maintenance-system/              ← DEPLOY_ROOT
├── .env                                 # 环境变量
├── MIGRATION.md                         # 本文件
├── backend/                             # FastAPI 后端
│   ├── app/
│   └── requirements.txt
├── frontend/
│   └── dist/                            # 构建产物，后端直接挂载
└── runtime/                             ← RUNTIME_ROOT，所有运行时数据
    ├── session_maintenance.db           # SQLite（健康任务、profile、脚本注册）
    ├── profiles/                        # Chrome 用户数据目录（按规范放这里）
    │   └── moren-chrome/
    ├── artifacts/runs/                  # 执行产物（日志、结果、config.json）
    ├── logs/                            # 应用日志
    └── scripts/uploaded/                # 已上传的执行脚本
```

## 常见问题

- **前端打不开？** → 确认 `frontend/dist/` 存在，没有则在前端目录执行 `npm run build`
- **脚本执行失败？** → 检查 Chrome 是否安装、profile 路径是否正确
- **MySQL 连不上？** → 确认 RDS 白名单已放行新机器 IP
- **端口被占用？** → 修改 `--port` 参数，同步更新防火墙规则
