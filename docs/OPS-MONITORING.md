# 监控与告警配置

## 探针：`tools/watchdog.py`

独立健康探针（仅标准库，后端宕机时仍能自检），三个检查项：

| 探针 | 检查内容 | 失败含义 |
|---|---|---|
| 后端 | `GET http://127.0.0.1:8081/api/health` 返回 200 且 body 含 `ok` | 服务进程/端口异常 |
| SQLite | `runtime/session_maintenance.db` 存在且可写 | 数据库丢失/锁定 |
| RDS | `MYSQL_HOST:3306` TCP 可达 | legacy cookie 链路断开 |

任一失败：推飞书卡片告警（`.env` 的 `FEISHU_WEBHOOK_URL`，红色模板），退出码非 0。

## 调度：计划任务 `SessionBackend-Watchdog`

- 命令：`D:\session-maintenance-system\backend\.venv\Scripts\pythonw.exe D:\session-maintenance-system\tools\watchdog.py`
- 频率：每 5 分钟一次（`/sc minute /mo 5`）
- `pythonw.exe` 无控制台窗口

### 手动运行 / 验证

```bat
cd /d D:\session-maintenance-system
backend\.venv\Scripts\python.exe tools\watchdog.py & echo %errorlevel%
```

输出三行 `[watchdog] 后端/SQLite/RDS: OK ...`，全 OK 退出码 0。

### 查看最近运行结果

```bat
schtasks /query /tn SessionBackend-Watchdog /v /fo LIST
```

关注 `上次结果` 字段：`0` 表示上次探活全部正常。

## 业务级告警（后端内置）

健康检测失败、任务风险等业务事件已通过 `notification_service.send_feishu_notification` 推飞书（卡片）。探针告警与业务告警互补：

- 业务告警：进程活着时，检测/任务层面的异常
- watchdog 告警：进程/数据库/网络层面的故障

## 日志

| 日志 | 路径 | 说明 |
|---|---|---|
| 应用日志（轮转） | `runtime/logs/backend.log` | 10MB × 5 自动轮转，含启动/迁移/uvicorn/业务日志 |
| 启动诊断 | `runtime/logs/boot.log` | 启动早期 stdout/stderr 兜底（正常启动后不再增长） |

> 所有运行时日志统一在 `runtime/logs/`，根目录不再产生 `backend-*.log`。
