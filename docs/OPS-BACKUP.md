# 备份与恢复手册

## 需要备份什么

| 对象 | 路径 | 说明 |
|---|---|---|
| **主业务库（最重要）** | `runtime/session_maintenance.db` | 任务、健康检测、修复单、profile、脚本注册、运行日志 |
| 环境配置 | `.env` | MySQL 口令、天巡云账号、飞书 webhook（**不进 git，务必单独备份**） |
| 上传的脚本 | `runtime/scripts/uploaded/` | 用户上传的执行脚本 |
| Chrome 用户数据 | `runtime/profiles/` | profile 会话数据（体积大，按需） |
| 执行产物 | `runtime/artifacts/runs/` | 任务执行结果（可重建，按需） |

> 前端 `frontend/dist` 可由源码 `npm run build` 重建；`backend/.venv` 可由 `pip install -r requirements.txt` 重建，均无需备份。

## SQLite 备份（核心）

SQLite 是单文件库，直接用文件拷贝会有写入锁与不一致风险。推荐两种方式：

### 方式一：SQLite 在线备份（推荐，无需停服）

```bat
cd /d D:\session-maintenance-system
backend\.venv\Scripts\python.exe -c "import sqlite3,os,datetime,shutil; src=r'D:\session-maintenance-system\runtime\session_maintenance.db'; d=datetime.datetime.now().strftime('%%Y%%m%%d'); bak=r'D:\session-maintenance-system\runtime\backup\session_maintenance_'+d+'.db'; os.makedirs(os.path.dirname(bak),exist_ok=True); sqlite3.connect(src).backup(sqlite3.connect(bak)); print('OK', bak)"
```

### 方式二：停写后拷贝（变更前快速备份）

```bat
taskkill /f /im python.exe   REM 先停后端
copy /y runtime\session_maintenance.db runtime\backup\session_maintenance_manual.db
restart_backend.bat          REM 重启
```

## 建议备份策略

- **每日一次**：用方式一生成 `session_maintenance_YYYYMMDD.db`，保留最近 30 天，旧文件删除。
- **每次重大变更前**（迁移、改脚本、清库）：手动方式一留一个时间点副本。
- **异地**：`.env` 与数据库备份副本定期拷贝到独立位置或对象存储（本机磁盘损坏时仍可恢复）。

> 阿里云 RDS MySQL 由云侧自动备份，无需本地处理；`ods_*` 表只读使用。

## 恢复步骤

1. 停后端：`schtasks /end /tn SessionBackend-Interactive`
2. 用备份文件覆盖：`copy /y <备份>.db runtime\session_maintenance.db`
3. 启动后端：`schtasks /run /tn SessionBackend-Interactive`
4. 验证：`curl http://127.0.0.1:8081/api/health` 200，且任务/检测列表数据正确
5. 若 schema 与旧库不一致，先 `alembic upgrade head` 再验证

> 恢复会覆盖当前数据，执行前先备份"当前损坏库"作为留证。
