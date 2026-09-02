# 启动入口与运维操作手册

> 生产环境唯一入口是**计划任务**，不要在生产机器上手动起 uvicorn 以免与计划任务冲突（端口 8081）。

## 启动体系总览

| 入口 | 用途 | 说明 |
|---|---|---|
| 计划任务 `SessionBackend-Interactive` | **生产唯一入口** | `cmd /c start_interactive.bat` → `run_server.py`（先 alembic 迁移再起 uvicorn），在交互会话运行，Chrome 有头窗口可见 |
| `start_interactive.bat` | 生产启动脚本 | 被计划任务调用；优先用 `backend\.venv\Scripts\python.exe`；日志由 run_server.py 写入 `runtime/logs/backend.log`（10MB×5 轮转） |
| `restart_backend.bat` | 生产重启脚本 | 杀掉 8081 监听进程 → `/end` 计划任务残留实例 → `/run` 重新拉起 |
| `start_backend.bat` | **开发** | 读 .env，跑迁移 + 前台起 uvicorn（`--migrate-only` 可只迁移） |
| `start_frontend.bat` | **开发** | 起前端 dev server（vite） |
| `start.vbs` | **开发** | 一次起后端 + 前端 dev，弹提示框 |

## 日常操作

### 启动（首次/停机后）

```bat
schtasks /run /tn SessionBackend-Interactive
```

### 重启（改代码/配置后）

```bat
restart_backend.bat
```

等价于：`taskkill` 8081 进程 → `schtasks /end /tn SessionBackend-Interactive` → `schtasks /run /tn SessionBackend-Interactive`。

> 直接 `schtasks /run` 重启往往失败——若上次实例未被清理，调度器会提示"任务正在运行中"并拒绝新实例。必须**先 `/end` 再 `/run`**。

### 停止

```bat
schtasks /end /tn SessionBackend-Interactive
```

### 确认运行状态

```bat
netstat -ano | findstr :8081 | findstr LISTENING
curl http://127.0.0.1:8081/api/health
```

## 端口与访问

- 后端 API / 前端静态页（`frontend/dist` 同端口托管）：`http://<机器IP>:8081`
- 开发前端 dev server：`http://127.0.0.1:5173`
- 端口由 `.env` 的 `APP_PORT` 控制（默认 8081），需防火墙放行内网访问

## 数据库

- 主业务库：SQLite `runtime/session_maintenance.db`（自动迁移 `alembic upgrade head`）
- 外部数据源：阿里云 RDS MySQL（`.env` 的 `MYSQL_*`，读取 `ods_cookie_playwright` 等 legacy 表）

详见 [OPS-BACKUP.md](./OPS-BACKUP.md) / [OPS-MONITORING.md](./OPS-MONITORING.md) / [OPS-SECURITY.md](./OPS-SECURITY.md)。
