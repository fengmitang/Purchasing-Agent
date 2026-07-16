# Codex 全流程开发执行手册

## 1. 文档关系和优先级

根目录 `AGENTS.md` 是不可降级的硬约束；当前已确认 Issue 定义任务范围，需求/架构/数据库/API 文档定义业务与公共契约，目标模块代码和本手册提供实现上下文。任意来源冲突时停止并说明，不自行选择。

```text
README.md                  项目入口和启动方式
AGENTS.md                  强制开发规则
docs/requirements.md       需求和验收真源
docs/architecture.md       模块与依赖方向
docs/database-design.md    表、约束和迁移基线
docs/api-contracts.md      公共接口和 Schema
docs/decisions.md          MVP 业务默认值
docs/backlog.md            首批可执行任务
```

不要要求 Codex 一次完成整个系统。以一个满足 Definition of Ready 的 Issue 为单位工作。

## 2. 固定技术和边界

- Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2 async、asyncmy、Alembic、MySQL 8.0。
- HTTPX + Tenacity 调用外部接口；APScheduler + MySQL 任务表处理提醒和重试。
- React + TypeScript + Ant Design 管理端后置到业务接口稳定后。
- 自定义有限状态 Agent，不采用 LangGraph、AutoGen 或 CrewAI。
- 模块化单体、Docker Compose + Nginx、GitHub Actions、Pytest 和 Ruff。

## 3. 两人协作

| 开发者 | 主责 | 典型模块 |
| --- | --- | --- |
| A | 工程底座、公共能力、权限、会话、Agent 和需求基础 | main/bootstrap/config、infrastructure、shared、agent、requirement、audit 基础 |
| B | 主数据、名单、推荐和采购闭环 | product、supplier、whitelist、blacklist、recommendation、approval、purchase、delivery、inspection、inbound |
| 共同 | 契约、状态、数据库设计、迁移链、CI 和发布 | docs、migrations、公共 Schema |

每个 Issue 一名负责人、一名审查者。先确定公开 Service 和 Pydantic Schema，再并行实现调用方和被调用方。避免同时修改同一枚举、核心状态机、公共 Schema 或数据库表。

## 4. GitHub 工作流

```text
main                         唯一长期分支，保持稳定可演示
feature/<issue>-<name>       功能
fix/<issue>-<name>           缺陷
docs/<issue>-<name>          文档
chore/<issue>-<name>         工程配置
```

1. Issue 达到 Ready 并指定负责人/审查者。
2. 从最新 `main` 创建短分支。
3. Codex 先分析并输出计划，人工确认后实施。
4. 运行定向测试和必要的全量检查。
5. 人工检查 diff、迁移、契约、测试与敏感信息。
6. 向 `main` 提 PR，描述使用 `Closes #<issue>`。
7. 另一名开发者批准、CI 通过、讨论解决后 Squash and merge。

Codex 不得自行 push、合并、删除分支、修改生产数据或发布。

## 5. Codex 五阶段协议

| 阶段 | Codex | 人工 |
| --- | --- | --- |
| 理解 | 阅读规则、Issue、文档、代码和分支差异 | 确认范围/依赖 |
| 计划 | 列出文件、数据、接口、测试和风险 | 批准或纠正 |
| 实现 | 小步修改和定向验证，不越界重构 | 查看 diff/日志 |
| 自检 | 检查分层、权限、事务、幂等、审计和安全 | 审查业务关键点 |
| 汇报 | 真实列出改动、命令结果、风险和未完成 | 决定合并/返工/拆 Issue |

## 6. Definition of Ready

- 目标、背景、负责人和审查者明确；
- 输入、输出、业务规则和验收标准可测试；
- 允许和禁止修改范围已列出；
- 依赖表、Service、Schema 和前置 Issue 已确认；
- 权限和数据范围已说明；
- 数据库/API/公共契约变化已标记；
- 没有阻塞性需求歧义。

## 7. Definition of Done

- 只实现 Issue 范围，满足关联需求和验收；
- 遵守 Router/Service/Repository 和 Agent 边界；
- 文档、接口和迁移同步；
- 迁移可从空库执行且只有一个 head；
- 测试覆盖正常、异常、权限、状态、幂等和相关边界；
- Ruff、格式检查和 CI 通过；
- 无真实密钥和敏感业务数据；
- 另一名开发者批准，遗留事项已拆成新 Issue。

## 8. 质量与审查清单

- Router 是否直接访问 ORM/Repository？
- Agent 是否绕过 Business Service 或执行高风险写操作？
- 权限和数据范围是否在 Service 校验？
- 状态变化是否经过状态机并追加历史？
- 事务、并发、幂等和审计是否正确？
- 查询是否有 N+1、全表扫描、无分页或不稳定排序？
- 金额是否被转成 float？
- 日志、Prompt、测试和附件是否泄露敏感信息？
- Alembic 是否单 head，upgrade/downgrade 是否经过检查？
- 测试命令是否真实运行，失败是否被如实报告？

## 9. 阶段计划

| 阶段 | 目标 | 集成出口 |
| --- | --- | --- |
| M1 | 工程、数据库、配置、日志、测试和 CI | `/health`、空库迁移、CI |
| M2 | 产品、供应商、名单、历史、权限和审计 | 管理 API 和基础查询 |
| M3 | 会话、抽取、完整性、Handler 和联合检索 | 需求草稿与推荐入口 |
| M4 | 评分、替代、正式提交和楼长审批 | 需求到审批通过 |
| M5 | 订单、交付、验收、入库和黑名单闭环 | 批准到完成 |
| M6 | 飞书、通知、部署、端到端测试 | 试运行 |

首批 M1/M2 的详细任务见 `docs/backlog.md`。
