# Cookie 管理中心

## 功能

这是一个 Flask + MySQL 的内网管理后台，支持：

- 新增、编辑、删除任务
- 修改账号和密码
- 启用、停用定时探测
- 立即探测 Cookie
- 立即执行刷新脚本
- 查看执行状态、最近错误和运行记录
- 每 5 秒自动刷新页面状态
- 查看按 `(site, account)` 去重后的 Cookie 信息

站点脚本仍然是普通 Python 文件，不使用基类。你只需要在
`refresher/sites/` 中维护具体登录逻辑。

## 运行结构

```text
浏览器
  │
  ▼
Flask 管理后台
  ├── 任务 CRUD
  ├── 启停任务
  ├── 手动探测
  ├── 手动刷新
  └── 查询运行状态
        │
        ▼
后台线程池
  ├── requests 探测 Cookie
  └── importlib 调用 refresher.sites.site_xxx.refresh(task)
        │
        ▼
MySQL
  ├── cookie_tasks      任务配置与当前状态
  ├── crawler_cookies   Cookie 数据
  └── task_runs         每次执行记录
```

主进程同时启动 Flask 和定时调度线程。调度器每隔
`PROBE_INTERVAL_HOURS` 小时读取数据库中 `enabled=1` 的任务：

```text
读取 Cookie
→ 请求 probe_url
→ 状态码属于 ok_statuses：记录成功
→ 状态码异常或请求失败：自动提交刷新脚本
```

同一个任务同一时间只允许一个后台操作，避免重复点击导致多个浏览器实例。

## 数据库设计

执行 [storage/schema.sql](storage/schema.sql) 创建三张表。

### cookie_tasks

保存前端登记的任务配置：

- 任务名称、站点标识和账号标识
- 登录账号和密码
- 探测地址、正常状态码、超时
- 刷新脚本模块名
- Edge/CDP 等高级参数
- 启停状态、最近结果和错误

唯一键：

```text
(site, account)
```

### crawler_cookies

保存刷新脚本采集的 Cookie，同样按 `(site, account)` 唯一。

PDD 只登记一个探测任务 `pdd-home`。`site_pdd.py` 登录一次后，在一个事务中写入：

- `pdd-home`
- `pdd-marketing`

### task_runs

记录手动和自动执行的探测、刷新结果，包括：

- queued / running / success / failed
- HTTP 状态码
- 开始、结束时间
- 成功信息或错误信息

## 前端交互

管理页入口：

```text
http://127.0.0.1:5000
```

任务表支持搜索和状态筛选。新增或编辑时可填写：

- 任务名称
- 站点标识
- 账号标识
- 登录账号、密码
- 探测网址
- 正常状态码
- 刷新脚本
- 是否启用
- 登录网址、浏览器路径、用户目录、CDP 端口等高级配置

刷新脚本名称必须是已存在的：

```text
refresher.sites.site_xxx
```

网页不能输入任意文件路径或系统命令作为脚本。

## 刷新脚本接口

每个脚本只需要保留一个入口：

```python
def refresh(task: dict) -> bool:
    username = task["username"]
    password = task["password"]
    # 登录、采集 Cookie、调用 save_cookies(...)
    return True
```

一个登录产生多份 Cookie 时，脚本自行一次性写入。

## 启动

1. 创建 MySQL 表：

```powershell
mysql -h 127.0.0.1 -u root -p crawler < storage/schema.sql
```

2. 创建 `.env` 并配置 MySQL。

3. 安装依赖并启动：

```powershell
python -m pip install -r requirements.txt
playwright install chromium
python main.py
```

PDD 使用本机 Edge 和 CDP，应在 Windows 环境运行。
