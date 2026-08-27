# Cookie 一键上报（Chrome 扩展）

与「Cookie 同步助手」（任务驱动，读同事浏览器 cookie）不同，本扩展是**手动驱动**：

> 你自己登录了某个店铺页面，点一下扩展 → 自动抓当前页面 Cookie → 手动填渠道/店铺/手机号/DNS → 上报入库，供采集脚本读取。无需任务调度、无需映射表、无需同事协同。

---

## 一、安装

1. 打开 `chrome://extensions`
2. 右上角开启 **开发者模式**
3. 点击 **加载已解压的扩展程序**，选择本文件夹 `cookie-quick-upload`
4. 点扩展图标 → **设置**：
   - 后端地址：`http://127.0.0.1:8081`（与后端 `.env` 的 `APP_PORT` 一致）
   - API Key：后端 `COOKIE_SYNC_API_KEY` 留空则留空；已配置则填一致的值

## 二、使用

1. 打开已登录的目标店铺页面（http/https）
2. 点扩展图标，自动抓取当前页面 Cookie（列表脱敏，只显示名称）
3. 填写定位字段：
   - 渠道 channel（必填）
   - 店铺 shop_name（可空）
   - 手机号 mobile_phone（可空）
   - DNS（必填，默认预填当前域名，可改）
4. 点 **上报入库** → 后端按 `(channel, shop_name, mobile_phone, dns)` 先查后改写入 `ods_cookie_playwright`：已存在则覆盖更新、不存在则新增，页面提示「新增/更新 N 条 Cookie」

## 三、没抓到 Cookie

Cookie 未就绪时，点 **刷新页面并重新获取**：扩展会刷新当前标签页，稍候自动重新抓取。

## 四、与后端契约

| 项 | 值 |
|---|---|
| 接口 | `POST {后端地址}/api/cookies/manual` |
| 鉴权 | 请求头 `X-API-Key`（后端 `COOKIE_SYNC_API_KEY` 留空时无需） |
| Body | `{channel, shop_name, mobile_phone, dns, cookies, collected_at}` |
| 返回 | `{ok, stored, is_new}`（is_new=true 新增 / false 覆盖更新） |
| Cookie 格式 | `chrome.cookies` 原生字段（name/value/domain/path/secure/httpOnly/expirationDate/sameSite） |

> Cookie 等同登录凭证，请仅在内网使用，后端务必配置 `COOKIE_SYNC_API_KEY`。
> 注意：API Key 以明文保存在 `chrome.storage.local`（与兄弟扩展一致），未加密；请勿在多用户共享的电脑上使用。
