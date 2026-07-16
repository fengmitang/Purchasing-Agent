# 数据中心采购全流程自动化 Agent

## 1. 项目简介

本项目用于建设一个面向数据中心采购业务的全流程自动化 Agent。

系统以自然语言交互为入口，支持采购需求收集、信息补充、历史采购查询、白名单推荐、黑名单过滤、楼长审批、采购执行、供应商交付跟踪、到货验收和商品入库等业务流程。

项目采用轻量化、模块化、可扩展的设计，不依赖 Agent 编排框架。大模型负责自然语言理解、字段抽取和结果解释，业务程序负责权限、规则、状态流转、数据库写入和审计。

## 2. 核心功能

- 自然语言提交采购需求
- 采购需求字段抽取
- 缺失信息识别与多轮追问
- 采购白名单查询
- 历史采购记录检索
- 产品推荐与推荐依据展示
- 停产、下架产品替代推荐
- 非推荐产品补充说明
- 楼长审批、驳回、退回补充和转交
- 采购订单与供应商管理
- 供应商交付时间线
- 延期和异常交付记录
- 到货验收、拒收、退换货和入库
- 产品、供应商和产品—供应商组合黑名单
- 黑名单有效期、到期失效和审计
- 飞书机器人、消息卡片和通知集成
- 操作日志与全过程审计

## 3. 技术栈

### 后端

- Python 3.12
- FastAPI
- Pydantic 2
- SQLAlchemy 2
- Alembic
- MySQL 8.0
- asyncmy
- HTTPX
- Tenacity
- APScheduler

### Agent

- 自定义显式流程
- 自定义状态机
- Handler 注册机制
- 固定 Prompt 模板
- Pydantic 结构化输出
- 普通 Python 函数调用业务服务
- 不使用 LangGraph、AutoGen、CrewAI 等 Agent 框架

### 前端

- React
- TypeScript
- Ant Design

### 集成与部署

- 飞书企业自建应用
- 飞书机器人
- 飞书消息卡片
- Docker Compose
- Nginx
- GitHub Actions

### 测试与质量

- Pytest
- pytest-asyncio
- Ruff
- 可选：Mypy

## 4. 系统架构

本项目采用模块化单体架构。

```text
飞书机器人 / Web 管理后台
            │
            ▼
         FastAPI
            │
 ┌──────────┼──────────┐
 │          │          │
 ▼          ▼          ▼
Agent      采购业务    权限与审计
模块        模块        模块
 │          │          │
 └──────────┼──────────┘
            ▼
          MySQL
```

标准调用关系：

```text
Router -> Service -> Repository -> MySQL
```

Agent 调用关系：

```text
AgentService
  -> AgentHandler
    -> BusinessService
      -> Repository
        -> MySQL
```

## 5. 设计原则

1. `main.py` 不包含业务逻辑。
2. Router 只负责 HTTP 参数接收和响应。
3. Service 负责业务规则、权限和事务。
4. Repository 只负责数据库访问。
5. Agent Handler 不直接访问数据库。
6. Agent 不直接修改采购状态。
7. Agent 不直接使黑名单或白名单生效。
8. 大模型输出必须经过 Pydantic 校验。
9. 程序控制业务流程，大模型不自由决定执行顺序。
10. 正式业务事实必须存储在 MySQL 中。
11. 所有高风险写操作必须记录审计日志。
12. 新增功能优先新增模块或 Handler，不修改 Agent 主循环。

## 6. 项目目录

```text
procurement-agent/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   ├── config.py
│   ├── api/
│   ├── agent/
│   │   ├── service.py
│   │   ├── context.py
│   │   ├── state_machine.py
│   │   ├── schemas.py
│   │   ├── prompts.py
│   │   ├── handlers/
│   │   └── extractors/
│   ├── modules/
│   │   ├── requirement/
│   │   ├── product/
│   │   ├── supplier/
│   │   ├── whitelist/
│   │   ├── blacklist/
│   │   ├── recommendation/
│   │   ├── approval/
│   │   ├── purchase/
│   │   ├── delivery/
│   │   ├── inspection/
│   │   ├── inbound/
│   │   └── audit/
│   ├── integrations/
│   │   ├── feishu/
│   │   ├── llm/
│   │   └── storage/
│   ├── infrastructure/
│   └── shared/
├── migrations/
├── tests/
├── scripts/
├── docs/
├── AGENTS.md
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## 7. Agent 主流程

```text
用户输入采购需求
        ↓
识别业务场景
        ↓
抽取结构化字段
        ↓
检查字段完整性
   ├── 不完整：生成补充问题
   └── 完整
        ↓
查询有效黑名单
        ↓
查询白名单和历史采购记录
        ↓
执行候选产品评分
        ↓
生成推荐解释
        ↓
用户选择产品
        ↓
生成采购需求草稿
        ↓
用户确认提交
        ↓
进入楼长审批流程
```

Agent 只负责：

- 意图识别
- 字段抽取
- 歧义识别
- 补充问题生成
- 推荐结果解释
- 审批摘要生成
- 黑名单申请信息抽取

业务程序负责：

- 权限判断
- 黑名单过滤
- 白名单查询
- 推荐排序
- 金额计算
- 状态变更
- 审批提交
- 正式数据写入
- 验收入库
- 审计记录

## 8. 环境要求

建议环境：

```text
Python >= 3.12
MySQL >= 8.0
Docker >= 24
Docker Compose >= 2
```

MySQL 建议配置：

```text
字符集：utf8mb4
排序规则：utf8mb4_0900_ai_ci
存储引擎：InnoDB
```

## 9. 本地开发

### 9.1 克隆仓库

```bash
git clone git@github.com:<owner>/procurement-agent.git
cd procurement-agent
```

### 9.2 创建虚拟环境

```bash
python -m venv .venv
```

Windows：

```bash
.venv\Scripts\activate
```

Linux/macOS：

```bash
source .venv/bin/activate
```

### 9.3 安装依赖

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### 9.4 配置环境变量

复制示例文件：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

示例配置：

```env
APP_ENV=development
APP_NAME=procurement-agent
DEBUG=true

DATABASE_URL=mysql+asyncmy://procurement:procurement@127.0.0.1:3306/procurement

SECRET_KEY=replace-with-a-secure-secret

LLM_PROVIDER=openai_compatible
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
```

不得将真实密钥提交到 GitHub。

### 9.5 启动 MySQL

使用 Docker Compose：

```bash
docker compose up -d mysql
```

### 9.6 执行数据库迁移

```bash
alembic upgrade head
```

### 9.7 启动后端

```bash
uvicorn app.main:app --reload
```

默认访问地址：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

## 10. 测试与代码检查

运行全部测试：

```bash
pytest -q
```

运行指定模块测试：

```bash
pytest tests/unit/whitelist -q
```

代码检查：

```bash
ruff check .
```

格式检查：

```bash
ruff format --check .
```

自动格式化：

```bash
ruff format .
```

## 11. GitHub 协作流程

本项目使用以下分支：

```text
main
develop
feature/*
fix/*
docs/*
```

规则：

- `main` 保存稳定发布版本。
- `develop` 保存日常集成版本。
- 功能分支必须从 `develop` 创建。
- 禁止直接向 `main` 和 `develop` 推送。
- 每项任务必须关联 GitHub Issue。
- 每个 Pull Request 必须由另一位开发者审查。
- GitHub Actions 未通过不得合并。
- 默认使用 Squash and merge。

创建功能分支示例：

```bash
git checkout develop
git pull origin develop
git checkout -b feature/12-product-whitelist
```

提交示例：

```bash
git add .
git commit -m "feat(whitelist): implement product whitelist query"
git push -u origin feature/12-product-whitelist
```

Pull Request 目标分支：

```text
feature/12-product-whitelist -> develop
```

PR 描述中填写：

```text
Closes #12
```

## 12. Codex 使用规范

Codex 开发前必须阅读：

1. `AGENTS.md`
2. `docs/requirements.md`
3. `docs/architecture.md`
4. `docs/database-design.md`
5. `docs/api-contracts.md`
6. 当前 GitHub Issue

推荐首先向 Codex 输入：

```text
先不要修改代码。

请阅读 AGENTS.md、项目文档和当前 GitHub Issue，分析需要修改的文件、数据库变更、接口影响、测试计划和潜在冲突。

严格限制在 Issue 允许修改的范围内，先输出实施计划，等待确认。
```

确认后再执行：

```text
按照已确认的计划完成当前 GitHub Issue。

不得修改任务范围外文件。完成后运行测试，并列出修改文件、测试结果和遗留风险。
```

## 13. 数据库迁移规范

- 所有数据库结构变更必须使用 Alembic。
- 已合并到 `develop` 的迁移文件不得修改。
- 创建迁移前必须同步最新 `develop`。
- 合并前执行：

```bash
alembic heads
```

正常情况下应只有一个 head。

执行迁移：

```bash
alembic upgrade head
```

回退一个版本：

```bash
alembic downgrade -1
```

## 14. 主要文档

- `AGENTS.md`：Codex 和开发人员共同遵守的开发规则
- `docs/requirements.md`：软件需求
- `docs/architecture.md`：系统架构
- `docs/database-design.md`：数据库设计
- `docs/api-contracts.md`：模块接口契约
- `docs/development-guide.md`：详细开发流程

## 15. 当前开发阶段

当前项目处于初始开发阶段，建议按以下顺序建设：

1. FastAPI 工程底座
2. MySQL、SQLAlchemy 和 Alembic
3. 统一异常、日志和审计
4. 产品与供应商主数据
5. 黑白名单及历史采购数据
6. Agent 会话和 Handler 机制
7. 采购需求收集
8. 推荐与审批
9. 采购、交付、验收和入库
10. 飞书集成
11. 系统测试与上线部署

## 16. 安全说明

- 禁止提交 `.env`。
- 禁止提交数据库密码、API Key 和 Token。
- 禁止在 Prompt 中写入密钥。
- 所有外部回调必须验签。
- 所有写操作必须进行权限校验。
- 黑名单、审批和入库等高风险操作必须进行审计。
- 上传文件必须进行类型、大小和访问权限检查。

## 17. License

本项目为内部私有项目，未经授权不得复制、分发或用于其他用途。
