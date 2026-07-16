# 数据中心采购全流程自动化 Agent

面向数据中心采购业务的模块化单体系统。系统以自然语言为入口，覆盖需求收集、名单与历史检索、可解释推荐、楼长审批、采购执行、交付、验收、入库和全过程审计。

当前仓库处于**文档基线完成、M1 工程底座待开发**状态。尚未实现的启动命令和 API 不应被视为可用功能。

## 核心原则

- LLM 负责理解、抽取和解释；确定性程序负责流程、硬过滤、评分、权限和状态。
- 正式事实保存在 MySQL；Agent、Router 和 LLM 不直接写数据库或改变正式状态。
- 强制调用方向：`Router -> Service -> Repository -> MySQL`。
- 高风险操作必须经过身份/数据范围校验、明确确认、幂等控制和审计。
- MVP 采用模块化单体、显式状态机和 Handler，不使用 Agent 编排框架。

## 固定技术栈

- Python 3.12、FastAPI、Pydantic 2
- SQLAlchemy 2 异步模式、asyncmy、Alembic、MySQL 8.0
- HTTPX、Tenacity、APScheduler + MySQL 任务表
- Pytest、pytest-asyncio、Ruff、GitHub Actions
- React + TypeScript + Ant Design（管理端后置）
- Docker Compose + Nginx

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Codex 和开发者必须遵守的强制规则 |
| [需求基线](docs/requirements.md) | FR/BR/AI/AC、状态、MVP 范围和追踪矩阵 |
| [系统架构](docs/architecture.md) | 模块边界、调用方向、数据流和阶段出口 |
| [数据库设计](docs/database-design.md) | 核心实体、字段约束、索引和迁移规范 |
| [API 契约](docs/api-contracts.md) | 公共类型、错误、分页和 Planned 接口 |
| [MVP 决策](docs/decisions.md) | SRS 待确认项采用的可开发默认值 |
| [开发执行手册](docs/codex-development-playbook.md) | 两人 + Codex 的 Issue/PR 工作协议 |
| [M1/M2 Backlog](docs/backlog.md) | 首批 12 个可执行开发任务 |
| [协作规范](docs/COLLABORATION.md) | 分支、职责、评审和日常节奏 |

## 开发路线

1. **M1 工程底座**：FastAPI、配置、MySQL/Alembic、日志、异常、测试和 CI。
2. **M2 主数据和名单**：产品、供应商、白/黑名单、历史、导入、权限和审计。
3. **M3 需求 Agent**：会话、抽取、完整性和联合检索。
4. **M4 推荐和审批**：评分、替代、正式提交和楼长审批。
5. **M5 采购闭环**：订单、交付、验收、入库和名单治理。
6. **M6 飞书和上线**：验签、卡片、通知、部署和端到端验收。

## Git 工作流

- `main` 是唯一长期分支，始终保持可启动、可测试和可演示。
- 从最新 `main` 创建 `feature/<issue>-*`、`fix/<issue>-*`、`docs/<issue>-*` 或 `chore/<issue>-*`。
- 日常改动通过 PR 合入 `main`，必须由另一名开发者审查并通过 CI；项目初始化提交可由负责人确认后直接推送。
- 默认 Squash and merge；每个 PR 使用 `Closes #<issue>`。

首个开发任务从 [Backlog #1](docs/backlog.md#1-初始化-fastapi-模块化单体工程) 开始。实现前必须先阅读 `AGENTS.md` 和关联文档。

## 安全

禁止提交 `.env`、密钥、真实报价、联系人、合同附件或生产数据。Word 源文件不进入 Git；仓库内中文版 Markdown 是版本化真源。

本项目为内部私有项目。
