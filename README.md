# 数据中心采购全流程自动化 Agent

面向数据中心采购业务的模块化单体系统。系统以自然语言为入口，覆盖需求收集、名单与历史检索、可解释推荐、楼长审批、采购执行、交付、验收、入库和全过程审计。

当前仓库已完成 M1 的 FastAPI、异步数据库、Alembic、统一日志与 API 异常底座，并通过 GitHub Actions 持续验证工程质量。业务模块及标记为 `Planned` 的 API 尚未实现。

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
| [数据库设计](docs/database-design-2.md) | 核心实体、字段约束、索引和迁移规范 |
| [API 契约](docs/api-contracts.md) | 公共类型、错误、分页和 Planned 接口 |
| [Agent 与采购后端接口约定](docs/agent-backend-interface-agreement.md) | 双方职责、采购草稿、历史供应商推荐和员工确认提交 |
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

## 本地开发

项目要求 Python 3.12。首次运行时安装应用及开发依赖：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

启动本地服务：

```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload
```

提交前执行与项目门禁一致的检查：

```powershell
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m alembic heads
```

未配置 `TEST_DATABASE_URL` 时，Pytest 会跳过需要一次性 MySQL 8 测试库的集成测试。使用可销毁的空测试库执行完整测试：

```powershell
$env:TEST_DATABASE_URL = "mysql+asyncmy://test_user:test_password@127.0.0.1:3306/purchasing_agent_test?charset=utf8mb4"
.venv\Scripts\python -m pytest -q
Remove-Item Env:\TEST_DATABASE_URL
```

不得将 `TEST_DATABASE_URL` 指向开发共享库、预生产库或生产库；集成测试会执行迁移降级并创建、删除探针表。

### 开发测试数据

先把本地开发数据库升级到最新结构，再预览并写入脱敏测试数据：

```powershell
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m scripts.seed_development_data --dry-run
.venv\Scripts\python -m scripts.seed_development_data
```

生成器固定创建 500 张采购申请：240 张参考历史表格中的设备类别和业务模式，260 张为同类模拟记录。员工、联系方式、供应商、地点、型号、价格和流程时间均为虚拟测试数据。脚本不会删除已有业务数据；完整执行后再次运行会直接返回已有结果，检测到部分写入时会拒绝继续，避免重复数据。

## CI 门禁

GitHub Actions 在提交到 `main`、面向 `main` 的 Pull Request 及手动触发时执行以下同组命令：

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m alembic heads
```

CI 使用隔离的 MySQL 8.0 Service 运行全部数据库集成测试，任一命令失败都会阻断。实现新任务前必须阅读 `AGENTS.md`、当前 Issue 和关联文档。

## 安全

禁止提交 `.env`、密钥、真实报价、联系人、合同附件或生产数据。Word 源文件不进入 Git；仓库内中文版 Markdown 是版本化真源。

本项目为内部私有项目。
