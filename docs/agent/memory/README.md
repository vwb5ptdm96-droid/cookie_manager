# 项目记忆（Agent Memory）落点

> Agent 排障时按 **本单 channel / shop / script** 加载相关片段，禁止整目录无差别倾倒。  
> **禁止**写入 cookie、密码、token、完整 headers 明文。

## 目录约定

```text
docs/agent/memory/
├── README.md                 # 本说明
├── 项目运转.md                # 全局：系统如何转、目录、状态机、红线摘要
├── scripts/                  # 按维护脚本沉淀的经验
│   └── _TEMPLATE.md
└── shops/                    # 按店铺/账号维度的经验
    └── _TEMPLATE.md
```

## 命名建议

| 类型 | 文件名示例 |
|------|------------|
| 脚本 | `scripts/拼多多-cookie.md`（与 `runtime/scripts` 主文件名对应） |
| 店铺 | `shops/PDD-母婴.md` 或 `shops/{channel}-{shop_slug}.md` |

## 谁写

| 来源 | 何时 |
|------|------|
| 人 | 已知坑、固定弹窗、业务约定 |
| Agent | SOLVED 后追加「有效模式」短记（平台可先人工审核再开自动写） |

## 加载策略（实现方）

1. 必载：`项目运转.md`  
2. 若实例包有 `main_file`：载 `scripts/` 下同名或 stem 匹配文件（若存在）  
3. 若有 channel+shop：载 `shops/` 下匹配文件（若存在）  
4. 单次总 token 超限时：截断历史段落，保留「有效模式 / 已知弹窗 / 禁止事项」

## 与 runtime 的区别

| | `docs/agent/memory` | `runtime/` |
|--|---------------------|------------|
| 进 git | 是（模板与已审阅记忆） | 否（`.gitignore`） |
| 内容 | 经验与约定 | 脚本实体、Profile、产物、DB |
| Agent 写 | 受控、脱敏 | 脚本落盘按 SOP；产物写 artifacts |
