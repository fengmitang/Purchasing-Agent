# 数据中心采购 Agent — Codex 开发规则

本文件适用于仓库内所有目录。若 GitHub Issue 与本文件冲突，必须停止实施并请求人工确认；不得自行降低权限、审计、事务、幂等或安全要求。

## 1. 开始任务前

必须依次阅读：

1. 当前 GitHub Issue 的完整内容；
2. `docs/requirements.md`；
3. `docs/architecture.md`；
4. `docs/database-design.md`；
5. `docs/api-contracts.md`；
6. 目标模块现有代码与测试；
7. 当前分支相对 `main` 的状态。

第一轮只输出需求理解、文件范围、接口/数据库影响、实施步骤、测试计划和风险。获得确认后才能修改文件。

## 2. 范围和协作

- 每个 Issue 只有一名负责人，另一名开发者负责审查。
- 仅修改 Issue 的“允许修改”范围；需要越界时先解释原因并等待批准。
- 公共 Schema、状态枚举、数据库设计和公开 Service/API 契约的变化，必须先更新对应文档并由另一名开发者确认。
- A 主责工程底座、公共能力、身份权限、Agent、会话与需求基础。
- B 主责产品/供应商、名单、推荐、审批、采购、交付、验收与入库。
- `docs/`、`migrations/`、`pyproject.toml`、部署配置及本文件属于共同审查范围。

## 3. 架构边界

强制调用方向：

```text
Router -> Service -> Repository -> MySQL
AgentService -> AgentHandler -> BusinessService -> Repository -> MySQL
IntegrationClient <- BusinessService
```

- `main.py` 只负责创建应用，不放业务逻辑。
- Router 只处理协议、参数和响应，不直接访问 ORM、Repository 或提交事务。
- Service 负责权限、数据范围、业务规则、状态机、事务、幂等和审计编排。
- Repository 只负责数据访问，不承载业务授权和状态决策。
- Agent Handler 只能调用受控 Business Service，不得直接访问数据库。
- LLM 只负责理解、抽取和自然语言解释；不得决定硬过滤、评分、审批或正式状态变化。
- 正式业务事实必须保存到 MySQL；会话上下文和 JSON 草稿不能成为唯一事实来源。

## 4. 数据和迁移

- 使用 Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2 异步模式、asyncmy、Alembic 和 MySQL 8.0。
- 所有结构变化必须通过 Alembic；已合入 `main` 的迁移不可修改。
- 新迁移前执行 `alembic heads` 并确保只有一个 head；合并前从空测试库执行 `alembic upgrade head`。
- 金额使用 `DECIMAL`，禁止转为 `float`；时间按 UTC 存储并在边界转换。
- 关键记录采用追加历史、版本或逻辑失效，禁止静默覆盖和物理删除审计事实。
- 写操作必须在 Service 内定义事务边界；重复请求使用业务唯一键或幂等键返回原结果。

## 5. Agent 和 LLM

- 首期不使用 LangGraph、AutoGen、CrewAI 等 Agent 编排框架，只使用显式 Scene/Stage、状态机和 HandlerRegistry。
- 结构化模型输出必须经过目标 Pydantic Schema 的 `model_validate`。
- Prompt 必须要求未知事实返回 `null`、歧义写入 `ambiguities`、不得编造。
- 模型调用设置超时、有限重试、脱敏日志和调用记录；失败时提供表单或规则化降级。
- 推荐顺序固定为：硬约束/兼容性校验 -> 有效黑名单过滤 -> 白名单与历史召回 -> 确定性评分 -> 快照 -> LLM 解释。
- 黑名单、审批、采购、验收和入库等高风险动作必须由人工明确确认并通过受控 Service。

## 6. 测试和完成门禁

每个功能 Issue 至少覆盖：

- 一个正常场景；
- 一个参数或业务异常场景；
- 权限不足和数据范围场景；
- 非法状态跳转场景（涉及状态时）；
- 重复请求/幂等场景（涉及写入时）；
- 事务失败回滚场景（关键写入）；
- 有效期、时间或数值边界场景（适用时）。

完成前运行受影响测试，并在条件允许时运行：

```bash
ruff check .
ruff format --check .
pytest -q
alembic heads
```

不得声称未实际运行的命令通过，不得删除失败测试或降低校验来换取通过。

## 7. 安全和审计

- 禁止提交 `.env`、真实密钥、真实报价、联系人、合同附件或生产数据。
- 所有写操作校验身份、角色、组织/楼宇数据范围、对象状态和并发版本。
- 飞书及外部回调必须验签、去重并设置超时；上传附件必须限制类型、大小、访问权限并预留恶意文件检测。
- 审批、名单、采购变更、导出、验收和入库记录操作人、角色、时间、对象、前后值、理由、请求 ID 和幂等键。
- 日志、模型输入输出和错误响应必须脱敏，不得暴露令牌、数据库连接串或无关个人信息。

## 8. 必须停止并确认

出现以下情况时停止修改：

- 需求互相矛盾或缺少决定实现的关键规则；
- 需要改变公开 Schema、状态枚举、主键或已确认接口；
- 需要修改 Issue 禁止范围；
- Alembic 出现多个 head、迁移链损坏或需要修改已合并迁移；
- 发现越权、数据丢失、生产影响或敏感信息风险；
- 无关测试失败且修复会扩大任务范围；
- 需要删除数据、重建数据库、强制推送、合并分支或发布生产。

## 9. Git 规则

- `main` 是唯一长期分支，始终保持可启动、可测试和可演示。
- 从最新 `main` 创建 `feature/<issue>-*`、`fix/<issue>-*`、`docs/<issue>-*` 或 `chore/<issue>-*`。
- 日常改动通过 PR 合入 `main`，默认 Squash and merge；项目初始化提交可由负责人确认后直接推送。
- Codex 不得自行 push、合并 PR、删除分支或修改生产环境。
