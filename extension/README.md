# Cookie 同步助手(Chrome 扩展)

把**同事电脑 Chrome 里长期有效的登录 Cookie**,按需同步到后端/数据库,供你的 Python 采集脚本使用。

> 背景:部分账号只能扫码登录,且登录态保存在公司其他同事的浏览器里(因高频使用长期有效)。你的采集脚本 Cookie 失效后,无需再找同事扫码,让本扩展去那边读一次 Cookie 入库即可。

---

## 🚀 一、整体架构

```
你的采集脚本 ──(1) POST /api/request {"domains":[...]}──▶ 后端服务(入库/建任务)
                                                        │
                                                        │ (2) 扩展轮询 GET /api/tasks
                                                        ▼
                    同事电脑 Chrome ──扩展──▶ 读取明文 Cookie
                                                        │
              (3) POST /api/tasks/{id}/report {cookies} ◀┘
                        │
                        ▼
                    后端写入数据库 ──(4) 你的脚本从库里读 Cookie 继续采集
```

- 同事**零感知**:扩展装好、设置一次即可,自动在后台工作。
- **按需触发**:只有你的脚本发起请求时,扩展才会真正去读 Cookie,不浪费资源。

---

## 📦 二、项目文件

| 文件 | 说明 |
|------|------|
| `manifest.json` | 扩展清单(MV3),声明权限 |
| `background.js` | 后台 Service Worker:读 Cookie、任务轮询、定时兜底、消息处理 |
| `popup.html` / `popup.js` | 扩展弹窗:状态查看 + 立即同步 |
| `options.html` / `options.js` | 设置页:后端地址、域名、间隔等 |
| `trigger.html` / `trigger.js` | 测试页:验证"外部消息触发"(需本地 HTTP 服务打开) |
| `mock_server.py` | 零依赖模拟后端,本地联调用(真实部署请替换为你的后端) |
| `cookies_store.json` | mock_server 落盘的 Cookie 数据(自动生成) |

---

## 🛠️ 三、安装扩展(自己电脑先测)

1. 打开 `chrome://extensions`
2. 右上角开启 **开发者模式**
3. 点击 **加载已解压的扩展程序**,选择本文件夹 `chrome扩展`
4. 点扩展图标 → **打开设置**:
   - 后端地址:`http://127.0.0.1:8000`(先用本地 mock)
   - 填写要同步的域名,如 `example.com`
   - 保存后点 **测试连接**

---

## 🧪 四、本地联调(5 分钟)

### 1. 启动模拟后端
```bash
python mock_server.py
# 监听 http://127.0.0.1:8000
```

### 2. 在扩展设置里确认
- 后端地址 `http://127.0.0.1:8000`
- 已填要同步的域名
- 「任务轮询」保持开启
- 点「测试连接」→ 应提示"✅ 后端可达"

### 3. 模拟采集脚本发起请求
```bash
curl -X POST http://127.0.0.1:8000/api/request \
  -H "Content-Type: application/json" \
  -d '{"domains": ["example.com"]}'
# 返回 {"task_id":"task_1",...}
```

### 4. 等待扩展轮询执行(默认每 30s 一次)
扩展发现待处理任务 → 读取你已登录网站的 Cookie → 上报。后端控制台会打印:
```
📥 收到同步请求 task_1: ['example.com']
📤 任务 task_1 完成,入库 12 条 Cookie
```

### 5. 查看结果
```bash
curl http://127.0.0.1:8000/api/status
```
或直接看生成的 `cookies_store.json`。

### 6. 触发模式也可选:扩展图标 → 立即同步(直接推送 `/api/cookies`)

---

## 🔌 五、后端 API 契约(需你实现的真实接口)

| 接口 | 方法 | 调用方 | 说明 |
|------|------|--------|------|
| `/api/ping` | GET | 扩展(测试连接) | 健康检查,返回 `{"status":"ok"}` |
| `/api/request` | POST | 你的采集脚本 | 入队同步任务。body:`{"domains":[...],"worker_ids":["同事A"]}`。`worker_ids` 省略=任意采集者,指定则每个采集者各建一个任务 → `{"task_ids":[...]}` |
| `/api/tasks?worker_id=xxx` | GET | 扩展(轮询) | 只返回派给该采集者的待处理任务 `{"tasks":[{"task_id","worker","domains"}]}`(定向匹配 + 广播任务) |
| `/api/cookies?domain=xx&worker_id=yy` | GET | 你的采集脚本 | 查某域名某采集者的 Cookie(按人取,便于入库映射) |
| `/api/tasks/{task_id}/report` | POST | 扩展 | 提交读取到的 Cookie,写入你的库。body:`{"cookies":[...], "collected_at":...}` |
| `/api/cookies` | POST | 扩展(直接推送) | 定时兜底/立即同步时,直接把 Cookie 写入库 |

- 鉴权:扩展支持配置 API Key,请求头带 `X-API-Key`。mock_server 用环境变量 `API_KEY` 开启。
- Cookie 对象格式 = `chrome.cookies` 原生字段(`name`/`value`/`domain`/`path`/`secure`/`httpOnly`/`expirationDate`/`sameSite`/`session`)。你的采集脚本通常只需要 `name`+`value`,按域名组装成 `requests` 的 cookie 字典即可。

### Python 采集脚本示例(真实后端下)
```python
import requests

BACKEND = "http://<你的后端>:8000"

def request_cookie_sync(domains):
    # 1) 请求同步
    r = requests.post(f"{BACKEND}/api/request",
                      json={"domains": domains}, timeout=5)
    r.raise_for_status()
    # 2) 轮询等待扩展入库(或直接查库,取到最新 Cookie)
    return r.json()["task_id"]
```

---

## 🖥️ 六、三种触发方式

| 方式 | 触发方 | 说明 |
|------|--------|------|
| **任务轮询(推荐)** | 你的脚本 → 后端 → 扩展 | 扩展定时问后端"有没有活",有才干活。实现"我发送请求才执行" |
| **外部消息** | 内网页面 | `chrome.runtime.sendMessage(扩展ID, {command:'sync'})`,需页面域名在 `externally_connectable.matches` 白名单,见 `trigger.html` |
| **定时兜底 / 立即同步** | 扩展自身 / 弹窗按钮 | 定期或手动直接把配置域名下的 Cookie 推给后端 |

---

## 📦 七、部署到同事电脑

> ⚠️ **多同事必须区分采集者**:每台电脑在扩展设置里填**不同的「采集者编号(worker ID)」**(如 同事A / 同事B)。
> 后端会按这个编号归属 Cookie,这样同事A 的 `store.weixin.qq.com` Cookie 和同事B 的同名 Cookie 互不混淆,
> 你做「Cookie → 业务表」映射时能明确知道这串 Cookie 来自哪位同事。留空则归为 `unknown`。

1. **手动加载(最简单,用于试点)**:把本文件夹发给同事,指导按第三节步骤加载。建议先本地试用 1 台。
2. **企业策略(最无感,推荐正式)**:
   - 走 Chrome 企业版策略(ExtensionInstallForcelist)把 CRX 强制推到同事浏览器。
   - 需要公司 IT/域控配合,同事完全无感知、无操作。
3. **开发者模式 + 打包 CRX**:用 `chrome://extensions` 的「打包扩展程序」生成 `.crx`。注意:普通 Windows 电脑对非商店/非企业托管 CRX 会拒绝安装,所以正式环境优先走企业策略。

> ⚠️ 文职同事机器上:**Chrome 必须处于运行状态**,扩展才能工作。可通过浏览器开机自启/组策略保证。

---

## ⚠️ 八、注意事项

- **Chrome 必须打开**:扩展寄生在浏览器里,浏览器没启动则无法工作。
- **alarm 最小 30 秒**:轮询间隔无法低于 30s(`chrome.alarms` 限制)。
- **域名匹配**:`chrome.cookies.getAll({domain})` 会命中该域名及其子域名(含 `www`)的 Cookie。
- **host_permissions 可收紧**:当前用 `<all_urls>` 方便测试;正式使用建议改为实际目标站点,如 `"*://*.example.com/*"`,降低权限暴露面。
- **安全**:Cookie 等同登录凭证。请务必:仅内网部署 + API Key + IP 白名单(后端做)+ 最小化同步域名。
- **本机防火墙**:若后端在服务器上,需放行对应端口,扩展才能跨机器访问。

---

## 🧪 九、待验证 MVP(可跳过)

如果以后想绕开扩展、走"复制 Profile + CDP 拉起"路线,仍需验证:
> 关闭 Chrome → 复制 `Local State` + `Default\Network\Cookies` → CDP 拉起 → 登录态是否保留。

当前扩展方案不需要做这个实验,因为它直接通过官方 API 读取明文 Cookie,不碰文件锁和加密。
