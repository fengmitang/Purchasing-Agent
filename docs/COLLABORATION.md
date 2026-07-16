# 两人协作规范

> 目标：以小 Issue、短分支和明确契约让 `main` 始终可启动、可测试和可演示。

## 1. 职责

| 开发者 | 主责 | 模块 |
| --- | --- | --- |
| A | 工程底座、公共能力、身份权限、Agent、会话与需求基础 | `main/bootstrap/config`、`infrastructure`、`shared`、`agent`、`requirement`、审计基础 |
| B | 主数据、名单、推荐和采购闭环 | `product`、`supplier`、`whitelist`、`blacklist`、`recommendation`、`approval`、`purchase`、`delivery`、`inspection`、`inbound` |
| 共同 | 公共 Schema、枚举、数据库、迁移链、CI 和发布 | `docs`、`migrations`、公共契约和工程配置 |

每个 Issue 只有一名负责人，另一名开发者是审查者。跨模块开发先确定 `docs/api-contracts.md` 中的公开 Service/Schema，再分别实现；不得跨模块直连 Repository。

## 2. 分支和 PR

```text
main                         唯一长期分支，日常通过 PR 合入
feature/<issue>-<name>       功能
fix/<issue>-<name>           缺陷
docs/<issue>-<name>          文档
chore/<issue>-<name>         工程配置
```

标准流程：

```text
Issue Ready -> 同步 main -> 短分支 -> 分析/计划 -> 实现/测试
-> 自检 diff -> PR 到 main -> 对方审查 -> CI -> Squash merge
```

- 一个分支只实现一个小目标；分支作者负责解决该分支冲突。
- 冲突必须按双方业务意图和现行契约合并，不得机械选择 ours/theirs。
- 公共枚举、Schema、核心状态机和同一数据库表避免并行修改。
- PR 必须关联 Issue，列出数据库/API 变化、测试实况、风险和遗留事项。
- `main` 发布由人工完成；Codex 不得 push、合并、删除分支或发布。

## 3. Issue 最低信息

- 目标和业务背景；负责人、审查者和前置依赖；
- 关联 FR/BR/AI/AC；
- 允许和禁止修改范围；
- 输入、输出、权限和数据范围；
- 数据库/API/公共契约影响；
- 可执行的验收标准和测试要求；
- 明确不包含内容。

不满足以上条件时不得开始编码。

## 4. 日常节奏

1. 开始前同步昨天结果、今日 Issue、公共文件和阻塞。
2. 接口契约变化先更新文档并由对方确认。
3. 每天至少一次在真实公开契约上联调；问题创建 Issue，不只留在聊天记录。
4. 收工前推送个人分支（由开发者人工操作）并记录测试结果。
5. 超过 15 分钟仍无法确认的业务规则、Schema 或冲突，立即共同决策并记录到 `docs/decisions.md`。

## 5. 合并门禁

- 改动未超出 Issue；
- 分层、权限、事务、状态、幂等和审计正确；
- 迁移单 head 且可从空库升级；
- 受影响测试、Ruff 和格式检查真实通过；
- 文档和公共契约同步；
- 没有密钥、真实采购数据或未授权附件；
- 审查意见全部解决，遗留工作已经拆分。

完整 Codex 工作协议和 DoR/DoD 见 [开发执行手册](codex-development-playbook.md)。
