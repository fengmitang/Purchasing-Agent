# 数据中心采购 Agent — Codex 开发规则

本文件适用于仓库内所有目录，是 Codex 和其他自动化开发工具必须遵守的仓库级规则。

任何实现都不得自行降低权限、数据范围、事务、幂等、审计、状态校验、工具白名单或安全要求。发现规则冲突、关键需求缺失或实现范围不明确时，必须停止相关修改并明确报告冲突点，不得自行猜测业务结论。

## 1. 文档优先级与事实来源

发生冲突时，按照以下优先级判断：

1. 本文件 `AGENTS.md`；
2. 当前已经确认的 GitHub Issue；
3. `docs/requirements.md` 和 `docs/decisions.md`；
4. `docs/architecture.md`；
5. `docs/database-design-2.md`；
6. `docs/api-contracts.md`；
7. `docs/agent-backend-interface-agreement.md`；
8. 目标模块的现有代码和自动化测试；
9. 当前分支相对 `main` 的差异。

业务规则以需求和决策文档为准；实际已经开放的接口、Agent Tool 和运行路径必须以当前代码及测试为准。

后端存在某个 HTTP 接口或 Service 方法，不等于该能力已经作为 Agent Tool 向模型开放。只有完成工具注册、动态授权、参数校验和测试后，才能把该能力描述为“Agent 可执行”。

## 4. 强制架构边界

### 4.1 普通业务请求

```text
Router
  -> Business Service
  -> Repository
  -> MySQL
```

### 4.2 Agent 聊天请求

```text
Agent Router
  -> AgentChatService
  -> IntentService
  -> AgentService
  -> ProcurementAgentRunner
  -> ToolExecutor
  -> AgentTool
  -> RequirementBackendProtocol
  -> Business Service
  -> Repository
  -> MySQL
```

### 4.3 外部系统调用

```text
Business Service
  -> Integration Client
  -> External System
```

强制要求：

* `app/main.py` 只暴露应用，不放业务逻辑。
* `app/bootstrap.py` 只负责应用装配、依赖构建、Router 注册和资源生命周期。
* Router 只负责协议、身份依赖、Header、参数校验和响应映射。
* Router 不得直接访问 ORM、Repository、数据库 Session 或提交事务。
* Business Service 负责权限、数据范围、业务规则、状态机、事务、幂等和审计。
* Repository 只负责查询、持久化、锁和分页，不负责权限、审批和状态决策。
* Integration Client 只负责外部协议、认证、超时、重试和响应转换，不承担业务决策。
* Agent Tool 不得直接访问数据库，必须通过公开 Backend Protocol 和 Business Service。
* 模型不得直接生成 SQL、操作 ORM、修改数据库状态或绕过 Service。
* 正式采购事实必须保存在 MySQL 中，Redis、对话历史、Prompt 和内存状态不得成为正式事实来源。

## 5. Agent 当前权威运行路径

当前采购 Agent 的权威执行路径位于：

```text
app/modules/agent/router.py
app/modules/agent/chat_service.py
app/modules/agent/chat_store.py
app/modules/agent/intent_service.py
app/modules/agent/service.py
app/modules/agent/runner.py
app/modules/agent/model.py
app/modules/agent/runtime.py
app/modules/agent/context.py
app/modules/agent/result.py
app/modules/agent/trace.py
app/modules/agent/skill_loader.py
app/modules/agent/tools/
app/modules/agent/procurement/
```

`ProcurementAgentRunner` 是当前模型决策和工具执行主循环。

除非 Issue 明确要求迁移，不得：

* 新建另一套 Handler 主循环；
* 新建另一套 Agent Orchestrator 取代 Runner；
* 在 Router 中实现 Agent 决策；
* 把固定 Workflow 伪装成模型自主决策；
* 在遗留 `orchestrator.py` 中继续增加与 Runner 重复的采购执行逻辑；
* 删除遗留路径前不检查实际引用和测试影响。

## 6. Agent 决策模型

本项目采用受控 Tool Calling Agent，而不是固定 Handler 流程。

模型可以根据以下内容自主决定下一步：

* 当前用户消息；
* 最近对话历史；
* 当前意图；
* Scene 和 Stage；
* 当前活动采购草稿状态；
* 本轮已经获得的工具结果；
* Runner 动态开放的工具集合；
* 已加载并允许注入的业务 Skill。

模型可以选择：

1. 调用一个或多个当前允许的工具；
2. 根据工具结果继续调用工具；
3. 向用户追问缺失或歧义信息；
4. 在已经完成目标时生成最终回复。

模型不能决定：

* 当前用户是否具有业务权限；
* 是否可以访问其他员工的数据；
* 正式采购状态如何转换；
* 是否绕过黑名单；
* 是否绕过版本冲突；
* 是否绕过幂等；
* 是否绕过必填字段；
* 是否绕过人工确认；
* 是否直接写入数据库；
* 是否把失败的工具调用描述为成功。

以上事项必须由 ToolExecutor、Agent Tool、Business Service、状态机和数据库约束共同保证。

## 7. Agent Tool 规则

### 7.1 当前已经注册的工具

当前采购 Agent Tool Registry 包含：

```text
create_requirement_draft
get_requirement_detail
update_requirement_draft
start_new_requirement
switch_active_requirement
```

当前未作为 Agent Tool 开放的能力包括：

```text
正式提交审批
取消或撤回采购草稿
分页查询本人采购申请
历史供应商推荐查询
白名单查询
黑名单操作
审批操作
采购下单
交付、验收和入库
```

即使对应后端 API 或 Service 已经实现，模型也不得声称已经执行这些未注册工具对应的动作。

### 7.2 动态工具授权

Runner 必须根据当前 Scene、Intent 和会话状态生成本轮 `allowed_tools`。

基本原则：

* `GENERAL_QUERY` 不开放任何业务工具；
* 没有活动草稿时，只开放创建第一张草稿所需工具；
* 已有活动草稿时，才开放查询、增量修改、新建另一张草稿和切换草稿；
* 查看、状态查询、确认提交或取消等场景，只开放当前真实允许执行的工具；
* 工具已注册但不在本轮 `allowed_tools` 中时，必须返回 `TOOL_NOT_ALLOWED`；
* 不得仅依靠 Prompt 约束高风险工具，必须通过代码白名单限制。

### 7.3 工具参数和执行

每个 Agent Tool 必须：

* 具有唯一稳定的工具名称；
* 具有准确且不夸大能力的工具说明；
* 使用 Pydantic `input_model`；
* 设置准确的 `is_write`；
* 通过 `model_validate` 校验模型参数；
* 通过公开 Backend Protocol 调用业务后端；
* 返回结构化 `ToolExecutionResult`；
* 使用稳定错误码；
* 不向模型返回密钥、连接串、SQL、堆栈或无关个人信息。

写工具还必须：

* 校验业务幂等键；
* 校验当前版本；
* 校验当前状态；
* 校验当前用户和数据范围；
* 阻止同一轮完全相同的重复写入；
* 记录审计信息；
* 只在后端确认成功后更新会话状态。

### 7.4 新增工具的同步修改清单

新增或修改 Agent 可执行能力时，必须同步检查：

1. `AgentTool` 实现；
2. 工具输入 Pydantic Schema；
3. `ToolRegistry` 注册；
4. Runner 的动态 `allowed_tools`；
5. `RequirementBackendProtocol` 或对应 Backend Protocol；
6. 同进程 Business Service Adapter；
7. 必要的外部 Backend Client；
8. Agent System Prompt；
9. 相关 `skills/*/SKILL.md`；
10. API 和 Agent 后端接口约定；
11. 正常、异常、权限、状态、版本和幂等测试；
12. 工具调用 Trace 和安全日志；
13. README 中的当前能力说明。

只完成其中一部分，不得把能力标记为 Agent 已实现。

## 8. Agent 循环和终止条件

Agent 主循环必须满足：

* 最大迭代次数有限；
* 每次模型调用只获得当前允许的工具 Schema；
* 工具调用结果必须返回模型后再由模型决定下一步；
* 终止错误出现时停止本轮循环；
* 达到迭代上限时停止，不得继续重复写入；
* 同一轮相同写操作必须被阻止；
* 模型没有调用工具时，回复仍需经过虚假成功声明保护；
* 不保存或暴露模型隐藏推理过程。

只有满足以下条件之一时，Agent 才能声称某个动作已经完成：

1. 对应工具实际执行成功；
2. 后端返回了成功结果；
3. 返回状态与所声称动作一致。

不得因为用户说“确认提交”“取消”“已经好了”或模型生成了成功措辞，就声称正式状态已经变化。

## 9. 会话、Redis 和正式事实

* MySQL 是采购草稿、采购状态、申请人、金额、版本和审计事实的唯一来源。
* Redis 用于短期聊天历史、会话状态、聊天幂等和会话锁。
* 仅在本地或测试环境显式允许使用内存 Store。
* 同一员工的同一会话必须串行处理。
* 不同会话可以并行处理。
* 会话键必须包含组织、员工和 `conversation_id`，禁止跨用户访问。
* 用户消息应具有 `PROCESSING`、`COMPLETED` 或 `FAILED` 状态。
* 失败消息不得作为成功历史回放给后续模型。
* 会话重置只清除短期会话和聊天状态，不得删除、取消或修改 MySQL 采购事实。
* HTTP 聊天路径不得让多个 Store 独立维护同一份活动草稿状态。
* `AgentChatService` 负责持久化聊天路径的短期状态；AgentService 在该路径中不得再次独立持久化同一状态。

## 10. Skill 和 Prompt

* Skill 是业务指导文本，不是权限控制器、状态机或数据源。
* Skill 不得扩大当前 Tool Registry 和 `allowed_tools` 提供的能力。
* Skill 中描述的能力必须与当前实际注册工具一致。
* Skill 不得让模型声称已经执行尚未接入的提交、取消、推荐或审批操作。
* `SkillManager` 初始化后必须显式调用 `load()`，确认 Skill 已被扫描和解析。
* 未调用 `load()` 时，不得假定 Markdown Skill 已经生效。
* Runner 只注入经过选择、启用且与当前场景相符的 Skill。
* 单个 Skill 解析失败不得影响其他 Skill，但必须记录安全错误。
* Prompt 中必须明确：未知事实不得编造，工具结果和后端数据是正式事实来源。
* Prompt、Skill 和模型返回内容不得包含密钥、Token、数据库连接信息或无关个人信息。
* 修改 Skill 时必须增加或更新加载测试和 Prompt 注入测试。

## 11. 数据库和迁移

* 使用 Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2 异步模式、asyncmy、Alembic 和 MySQL 8.0。
* 所有数据库结构变化必须通过新的 Alembic revision。
* 已合入 `main` 的迁移不得修改、重排或重命名。
* 新迁移前执行 `alembic heads` 并确保只有一个 head。
* 合并前使用可销毁的空测试库执行 `alembic upgrade head`。
* 涉及回退能力时检查 `downgrade`。
* 金额和精确数量使用 `Decimal`/`DECIMAL`，禁止转换为 `float`。
* 时间统一按 UTC 存储，在系统边界转换。
* 状态历史、审批记录、采购事件、交付事件和名单历史采用追加记录。
* 禁止静默覆盖或物理删除审计事实。
* 写操作必须由 Business Service 定义事务边界。
* 外部网络调用不得占用长数据库事务。
* 重复写请求必须通过幂等键或业务唯一约束返回原结果或稳定冲突。

## 12. 测试和完成门禁

每个功能 Issue 至少覆盖：

* 正常场景；
* 参数校验失败；
* 业务规则失败；
* 权限不足；
* 数据范围隔离；
* 非法状态；
* 并发版本冲突；
* 重复请求和幂等；
* 事务失败回滚；
* 时间、有效期、金额或数量边界；
* 安全错误不泄密。

Agent 相关 Issue 还必须覆盖：

* 模型不调用工具时的回复；
* 合法工具调用；
* 未授权工具调用；
* 不存在的工具；
* 工具参数校验失败；
* 相同写工具重复调用；
* 工具终止错误；
* 模型 Provider 响应格式转换；
* 最大迭代次数；
* 通用对话不开放业务工具；
* 虚假提交或虚假取消声明拦截；
* 同一会话串行和不同会话并行；
* 会话重置不影响 MySQL 业务事实；
* Skill 加载和注入；
* Trace 不包含敏感字段。

完成前运行受影响测试，并在条件允许时运行：

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m alembic heads
```

不得：

* 声称未实际执行的命令通过；
* 删除失败测试；
* 降低断言；
* 跳过关键校验；
* 使用 Mock 结果冒充真实集成验证；
* 因无关格式问题修改整个仓库。

## 13. 安全、审计和可观测性

* 禁止提交 `.env`、真实密钥、真实报价、真实联系人、合同附件或生产数据。
* 所有业务写操作必须校验身份、角色、组织、楼宇数据范围、对象状态和并发版本。
* 飞书及其他外部回调必须验签、去重、限时和安全失败。
* 附件必须限制类型、大小、访问权限，并预留恶意文件检测。
* 审批、名单、采购变更、导出、验收和入库必须记录操作人、角色、时间、对象、前后值、理由、请求 ID 和幂等键。
* Agent Trace 只记录事件、耗时、工具名称、错误码和必要标识。
* Agent Trace 不得记录模型隐藏推理、Authorization、完整 Prompt、完整用户消息、采购字段值或密钥。
* 日志、模型输入输出和错误响应必须脱敏。
* 不得把内部异常、堆栈、SQL 或连接信息返回给用户。
* 模型、Redis 或后端不可用时返回稳定、安全的公共错误。

## 14. 必须停止并报告

出现以下情况时，停止相关修改并报告：

* 需求、Issue 和文档互相矛盾；
* 缺少决定实现方式的关键业务规则；
* 需要改变公开 Schema、状态枚举、主键或稳定错误码；
* 需要修改 Issue 禁止范围；
* 需要让 Agent 获得新的高风险工具；
* 后端接口状态与 Agent Tool 状态不一致；
* 发现两个并行 Agent 主循环；
* Redis 和 MySQL 对同一正式事实产生冲突；
* Alembic 出现多个 head；
* 迁移链损坏；
* 需要修改已经合并的迁移；
* 发现越权、数据丢失、生产影响或敏感信息风险；
* 无关测试失败且修复会扩大当前任务范围；
* 需要删除数据、重建数据库、强制推送、合并分支或发布生产。

停止时必须说明：

1. 发现了什么；
2. 影响哪些文件和功能；
3. 为什么不能安全继续；
4. 推荐的处理方案；
5. 哪些部分已经完成并可保留。

## 15. Git 规则

* `main` 是唯一长期分支，必须保持可启动、可测试和可演示。
* 从最新 `main` 创建短分支。
* 分支命名使用：

```text
feature/<issue>-<name>
fix/<issue>-<name>
docs/<issue>-<name>
chore/<issue>-<name>
```

* 每个 PR 对应一个明确 Issue。
* PR 描述必须列出改动、接口影响、数据库影响、测试结果、风险和未完成项。
* 使用 `Closes #<issue>` 关联任务。
* 日常改动通过 PR 合入 `main`。
* 默认使用 Squash and merge。
* 不得将无关本地改动混入 PR。
* Codex 不得自行 push、合并 PR、删除分支、修改生产环境或发布。
