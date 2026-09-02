# 安全基线

> 本机为**内网生产机**，安全基线以内网隔离为第一道防线，其余按可接受风险处理。

## 敏感信息

| 项 | 位置 | 要求 |
|---|---|---|
| MySQL（RDS）口令 | `.env` 的 `MYSQL_PASSWORD` | 不进 git（`.gitignore` 已挡）、文件权限仅 Administrators、不在聊天/日志中明文扩散 |
| 天巡云账号密码 | `.env` 的 `TXY_PASSWORD` | 同上 |
| 飞书 webhook | `.env` 的 `FEISHU_WEBHOOK_URL` | 同上 |
| 扩展采集密钥 | `.env` 的 `COOKIE_SYNC_API_KEY` | 当前**未配置**（接口无鉴权）。如接口暴露到不可信网络必须配置并让后端强制校验 `X-API-Key` |

> `.env` 已在 `.gitignore` 中，`git status` 确认不会误提交。`backend/memory.zip`、`package.zip` 等历史打包物可能裹带敏感信息，如不再需要建议移出项目目录或清理。

## 网络暴露

| 面 | 现状 | 要求 |
|---|---|---|
| 后端端口 8081 | 绑定 `0.0.0.0`，防火墙放行 | 确认仅内网可达；前端页面**无登录**，属内网信任边界内的可接受风险 |
| 阿里云 RDS | `rm-*.mysql.rds.aliyuncs.com:3306` | 阿里云侧白名单**只放行本机（及明确需要的主机）IP**，严禁 `0.0.0.0/0` |
| 本机其他服务 | 3306/5432/6379 等 | 项目不直接使用，不对外暴露 |

## 日常守则

- 生产机器上不以交互方式把 `.env` 内容粘贴到外部服务（webhook 诊断等除外）。
- 改 `.env` 后用 `git check-ignore .env` 确认未被 git 跟踪。
- 推送代码前用 `git status` 确认无 `.env`、`*.db`、日志、`__pycache__` 等敏感/运行时文件混入。
- 不再使用的历史打包物（`*.zip`）与旧日志及时清理。

## 应急

- 怀疑泄密：立即轮换 `.env` 中所有口令（RDS 密码、天巡云、webhook、扩展密钥）。
- 修改后重启：`restart_backend.bat`。
