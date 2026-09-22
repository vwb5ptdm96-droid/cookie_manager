# 维护脚本目录（纳入 git）

上传包落在 `uploaded/<script_code>/<version>/`。

**不要**把 Profile 目录库、日志、SQLite、cookie 明文放这里。
`runtime/profiles`、`runtime/logs`、`runtime/artifacts` 仍被 gitignore。
