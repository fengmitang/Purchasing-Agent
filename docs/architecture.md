# 系统架构

## 1. 架构目标

项目采用模块化单体架构，在保持一次部署、统一身份、单一业务事务边界和轻量运维的同时，通过明确模块边界支持两人并行开发。

首期不使用：

* 微服务拆分；
* Kubernetes；
* 独立消息队列；
* 独立向量数据库；
* LangGraph、AutoGen、CrewAI 等 Agent 编排框架；
* 由固定 Handler 决定全部步骤的伪 Agent 工作流。

采购对话采用自研受控 Tool Calling Agent：

* 模型根据目标、上下文、会话状态和动态工具集合决定下一步；
* Runner 控制迭代次数和工具开放范围；
* ToolExecutor 校验工具权限和参数；
* Business Service 决定权限、业务状态、事务、幂等和审计；
* MySQL 保存正式采购事实；
* Redis 保存短期聊天上下文和 Agent 会话状态。

## 2. 系统总体结构

```text
                 员工
                  |
        +---------+---------+
        |                   |
   Web 管理端          飞书机器人
        |                   |
        +---------+---------+
                  |
                Nginx
                  |
               FastAPI
                  |
     +------------+-------------+
     |            |             |
 Agent 聊天    采购业务模块    身份/权限/审计
     |            |             |
     +------------+-------------+
                  |
        +---------+---------+
        |                   |
      Redis               MySQL
 短期会话/锁/幂等       正式业务事实
        |
   模型 Provider
Anthropic/OpenAI兼容接口
```

当前管理端可以后置开发。FastAPI、MySQL、Redis、模型 Provider 和必要的定时任务共同构成后端运行环境。

Docker Compose 和 Nginx 用于内网部署；生产配置不得依赖本地内存 Store。

## 3. 强制调用方向

### 3.1 普通业务接口

```text
Router
  -> Business Service
  -> Repository
  -> MySQL
```

### 3.2 Agent 聊天接口

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

### 3.3 外部系统

```text
Business Service
  -> Integration Client
  -> External System
```

### 3.4 禁止的调用方向

```text
Router -> Repository
Router -> ORM
Agent -> MySQL
AgentTool -> Repository
AgentTool -> ORM
Repository -> Service
IntegrationClient -> Repository
LLM -> SQL
LLM -> 正式状态修改
模块 A Repository -> 模块 B Repository
```

## 4. 分层职责

| 层或组件                     | 负责                                        | 禁止                           |
| ------------------------ | ----------------------------------------- | ---------------------------- |
| Router                   | HTTP/回调协议、身份依赖、Header、输入输出 Schema、分页参数    | ORM 查询、业务授权、事务提交、Agent 决策    |
| AgentChatService         | 会话锁、聊天幂等、历史消息、短期状态、意图调用、Agent 调用、结果保存     | 直接修改正式采购事实                   |
| IntentService            | 根据当前消息和历史识别本轮意图                           | 执行业务写入、生成正式状态                |
| AgentService             | 构建 AgentContext、确定 Scene/Stage、调用 Runner  | 直接访问数据库                      |
| ProcurementAgentRunner   | 构造 Prompt、动态开放工具、执行模型—工具循环、限制迭代           | 绕过 ToolExecutor、直接写业务数据      |
| Model Adapter            | 统一 Anthropic/OpenAI 兼容模型的文本和 Tool Call 格式 | 承担业务权限、状态机或数据库逻辑             |
| ToolRegistry             | 注册可供模型发现的工具和 Schema                       | 自动授权全部工具                     |
| ToolExecutor             | 工具白名单、参数校验、重复写阻断、安全错误转换                   | 代替 Business Service 判断正式业务状态 |
| AgentTool                | 把受控业务能力暴露给模型，转换参数和结果                      | 直接访问 ORM、Repository 或 MySQL  |
| Backend Protocol/Adapter | 隔离 Agent 与具体业务模块，实现同进程或远程调用适配             | 绕过 Business Service          |
| Business Service         | 权限、数据范围、业务规则、状态机、事务、幂等、审计                 | 返回 ORM 实体、信任模型决定             |
| Repository               | 查询、持久化、数据库锁、分页                            | 权限、审批、业务状态决策                 |
| Integration Client       | 外部协议、签名、超时、重试、响应转换                        | 业务决策、事务编排                    |
| SkillManager             | 加载和提供业务指导文本                               | 扩大工具权限、替代状态机                 |
| Trace                    | 记录结构化执行事件和耗时                              | 记录模型隐藏推理、密钥或完整业务字段           |

## 5. 模块边界

| 模块               | 负责                           | 不负责               | 主责               |
| ---------------- | ---------------------------- | ----------------- | ---------------- |
| `agent`          | 聊天会话、意图、上下文、模型决策循环、受控工具、短期状态 | 正式业务状态、数据库直写、审批决策 | A                |
| `requirement`    | 采购草稿、需求单、字段校验、版本、状态历史        | 产品推荐评分            | A                |
| `product`        | 分类、品牌、型号、规格、生命周期、替代关系        | 审批                | B                |
| `supplier`       | 供应商、产品关系、履约指标                | 名单生效决策            | B                |
| `whitelist`      | 白名单范围、版本、有效期和查询              | 自然语言推荐            | B                |
| `blacklist`      | 黑名单对象、证据、复核、生效、失效            | 让 LLM 直接生效        | B，Agent 草稿由 A 协作 |
| `recommendation` | 硬过滤、召回、评分、排序、证据和快照           | 创建正式采购单           | B                |
| `approval`       | 审批实例、任务、记录、权限和动作             | 修改采购订单明细          | B                |
| `purchase`       | 询价、订单、供应商选择和采购变更             | 直接入库              | B                |
| `delivery`       | 交付事件、延期和履约指标                 | 覆盖订单历史事实          | B                |
| `inspection`     | 验收、质量异常、拒收和退换货               | 修改名单              | B                |
| `inbound`        | 入库单、明细、数量幂等和外部同步             | 绕过验收              | B                |
| `audit`          | 操作、状态、工具和模型调用留痕              | 承载业务主数据           | A，共同使用           |
| `auth`           | 身份适配、角色和数据范围                 | 替代业务模块授权规则        | A                |
| `shared`         | 公共契约、异常、身份、分页、请求上下文和时钟       | 业务模块特有规则          | 共同审查             |

跨模块调用只允许依赖公开 Service Protocol 和 Pydantic Schema。

任何模块不得读取另一个模块的 Repository、SQLAlchemy Model 或内部事务对象。

## 6. 当前推荐目录

```text
app/
  main.py
  bootstrap.py
  config.py

  api/
    dependencies.py
    health.py
    middleware.py

  modules/
    agent/
      __init__.py
      router.py
      runtime.py
      chat_service.py
      chat_store.py
      chat_schemas.py
      intent_service.py
      intent_recognizer.py
      service.py
      runner.py
      model.py
      context.py
      result.py
      enums.py
      state_machine.py
      trace.py
      skill_loader.py

      tools/
        base.py
        registry.py
        executor.py
        requirement_tools.py

      procurement/
        protocols.py
        schemas.py
        service_backend.py
        backend_client.py
        idempotency.py
        session_store.py

    auth/
    requirement/
    product/
    supplier/
    whitelist/
    blacklist/
    recommendation/
    approval/
    purchase/
    delivery/
    inspection/
    inbound/
    audit/

  infrastructure/
    database/
    logging/
    tasks/

  shared/

skills/
  collect-procurement-requirement/
    SKILL.md
  confirm-procurement-requirement/
    SKILL.md
  recommend-historical-supplier/
    SKILL.md

migrations/
docs/
tests/
  agent/
  api/
  integration/
  cli/
```

每个业务模块按需包含：

```text
router.py
service.py
repository.py
models.py
schemas.py
enums.py
protocols.py
```

不得为尚未开发的模块批量创建空壳。

`app/modules/agent/runner.py` 是当前采购 Tool Calling 主循环。除非专门的迁移 Issue 明确批准，不再新建并行 Handler 或 Orchestrator 执行链。

## 7. Agent 运行时组件

### 7.1 Agent Router

负责：

* 接收聊天消息；
* 校验可信员工身份；
* 校验 `Idempotency-Key`；
* 校验 `conversation_id` 和消息 Schema；
* 调用 `AgentChatService`；
* 返回统一公共响应。

Router 不决定使用哪个工具，也不直接调用 RequirementService。

### 7.2 AgentChatService

负责一次聊天请求的外围编排：

1. 根据组织、员工和会话编号生成隔离的会话键；
2. 获取同一会话的串行锁；
3. 校验聊天请求幂等；
4. 读取聊天历史和短期采购状态；
5. 记录用户消息为 `PROCESSING`；
6. 调用 IntentService；
7. 调用 AgentService；
8. 保存 Agent 回复和新的短期状态；
9. 将用户消息更新为 `COMPLETED`；
10. 保存聊天幂等结果；
11. 发生失败时将消息标记为 `FAILED`。

同一会话串行执行，不同会话允许并行。

失败的消息不得作为成功上下文回放给模型。

### 7.3 IntentService

IntentService 识别当前消息的操作意图，例如：

```text
create_requirement
supplement_requirement
modify_requirement
view_requirement
confirm_submission
cancel_requirement
query_status
unknown
```

意图只是 Agent 上下文的一部分，不能直接引起数据库状态变化。

低置信度或解析失败时可以使用规则化降级，但降级结果仍必须经过 Runner 和工具权限控制。

### 7.4 AgentService

AgentService 负责：

* 获取或接收当前短期采购状态；
* 根据意图确定 Scene；
* 根据采购状态确定 Stage；
* 构造 `AgentContext`；
* 调用 `ProcurementAgentRunner`；
* 返回结构化 `AgentHandleResult`。

在 HTTP 聊天路径中，短期状态由 `AgentChatService` 的 Chat Store 持久化。不得让 AgentService 再独立保存另一份不同步的会话状态。

### 7.5 ProcurementAgentRunner

Runner 是当前 Agent 的核心循环，负责：

* 创建请求级 Trace；
* 加载最近对话；
* 根据上下文计算本轮允许工具；
* 构造 System Prompt；
* 注入允许的 Skill；
* 调用模型；
* 解析文本和 Tool Call；
* 通过 ToolExecutor 执行工具；
* 将工具结果返回给模型；
* 重复判断直到模型回复、终止错误或达到迭代上限；
* 阻止虚假提交和虚假取消声明；
* 返回最终 Scene、Stage、短期状态和 Trace。

Runner 不是固定业务 Workflow。

模型可以自主决定本轮是否调用工具、调用哪个允许工具、是否继续调用或向用户追问，但不能访问本轮未开放的工具。

### 7.6 Model Adapter

模型通过统一 `AgentModelProtocol` 接入。

当前适配器包括：

```text
AnthropicToolCallingModel
OpenAICompatibleToolCallingModel
```

模型适配器负责：

* 请求格式转换；
* Tool Schema 转换；
* Tool Call 解析；
* 文本块解析；
* 超时；
* 有限重试。

模型适配器不实现采购业务规则。

Provider、模型、Base URL 和密钥由服务端配置，客户端不得指定。

### 7.7 ToolRegistry 和 ToolExecutor

ToolRegistry 保存所有已注册工具，但注册不等于本轮授权。

ToolExecutor 在执行前完成：

1. 检查工具是否在当前 `allowed_tools`；
2. 检查工具是否已注册；
3. 使用工具 Pydantic Schema 校验参数；
4. 对写工具计算本轮指纹；
5. 阻止本轮相同写入；
6. 调用工具；
7. 转换后端错误为安全稳定结果；
8. 标记不可继续的终止错误。

Prompt 约束不能替代 ToolExecutor 的代码约束。

### 7.8 AgentTool

每个 AgentTool 包含：

```text
name
description
input_model
is_write
execute()
```

AgentTool 的职责是将单个受控业务能力暴露给模型。

AgentTool 必须通过 Backend Protocol 和 Business Service 获取或修改业务数据，不得直接访问 MySQL。

### 7.9 Backend Adapter

模块化单体中的默认调用路径为：

```text
AgentTool
  -> RequirementBackendProtocol
  -> RequirementServiceBackend
  -> RequirementService
```

这样可以避免 Agent 通过 HTTP 绕回同一个 FastAPI 进程。

当 Agent 独立部署或进行外部契约联调时，可以使用 `ProcurementBackendClient` 调用对应 HTTP API，但字段、错误码、幂等和权限语义必须与同进程 Adapter 保持一致。

## 8. Agent 决策循环

```text
收到用户消息
  |
  v
AgentChatService 获取会话锁
  |
  v
读取聊天历史和短期状态
  |
  v
IntentService 识别意图
  |
  v
AgentService 构建 AgentContext
  |
  v
Runner 根据 Scene/Intent/状态计算 allowed_tools
  |
  v
将目标、上下文、Skill 和工具 Schema 发送给模型
  |
  +-------------------------------+
  |                               |
模型不调用工具                 模型调用工具
  |                               |
生成回复                      ToolExecutor 校验
  |                               |
虚假成功声明保护              AgentTool 调用 Business Service
  |                               |
  |                           工具结果返回模型
  |                               |
  +---------------<---------------+
                  |
          达到完成条件
                  |
                  v
        保存回复和短期状态
                  |
                  v
             返回用户
```

Agent 循环必须具备最大迭代次数。

达到上限时停止执行，不继续重复写入，并向用户说明流程暂停。

## 9. Scene、Stage 和动态工具

### 9.1 Scene

当前 Scene 包括：

```text
GENERAL_QUERY
PROCUREMENT_REQUIREMENT
PROCUREMENT_STATUS
BLACKLIST
WHITELIST_QUERY
SUPPLIER_QUERY
```

Scene 用于描述当前任务上下文和限制工具范围，不代表必须进入一套固定 Handler。

### 9.2 Stage

当前 Stage 包括：

```text
INTENT_RECOGNITION
COLLECTING_INFORMATION
WAITING_FOR_CLARIFICATION
PRODUCT_SEARCH
WAITING_FOR_PRODUCT_SELECTION
WAITING_FOR_CONFIRMATION
SUBMITTED
COMPLETED
CANCELLED
```

Stage 用于表示当前会话或采购事实所处阶段。

正式状态必须以业务后端返回结果为准，不得仅根据模型文本修改 Stage。

### 9.3 当前动态工具策略

| 当前条件                | 开放工具                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| `GENERAL_QUERY`     | 不开放业务工具                                                                                                 |
| 查看草稿、状态查询、确认提交或取消意图 | `get_requirement_detail`                                                                                |
| 采购场景且当前没有活动草稿       | `create_requirement_draft`                                                                              |
| 采购场景且已有活动草稿         | `get_requirement_detail`、`update_requirement_draft`、`start_new_requirement`、`switch_active_requirement` |

工具授权必须由代码生成，不能只依赖 System Prompt。

## 10. 当前 Agent Tool 能力

### 10.1 已注册工具

| 工具                          | 类型     | 作用                        |
| --------------------------- | ------ | ------------------------- |
| `create_requirement_draft`  | 写      | 当前会话没有草稿时创建第一张真实采购草稿      |
| `get_requirement_detail`    | 读      | 读取当前活动草稿最新详情、版本、缺失项、冲突和风险 |
| `update_requirement_draft`  | 写      | 增量修改当前活动草稿                |
| `start_new_requirement`     | 写      | 保留原草稿并创建另一张不同采购草稿         |
| `switch_active_requirement` | 会话切换/读 | 切换到当前会话最近办理记录中的另一张草稿      |

### 10.2 后端已存在但当前未开放为 Agent Tool

| 能力       | 后端状态                | Agent Tool 状态 | 当前聊天能否执行 |
| -------- | ------------------- | ------------- | -------- |
| 正式提交审批   | 后端接口/Service 已设计或实现 | 未注册           | 否        |
| 取消采购草稿   | 后端接口/Service 已设计或实现 | 未注册           | 否        |
| 分页查询本人申请 | 后端接口/Service 已设计或实现 | 未注册           | 否        |
| 历史供应商推荐  | 后端查询能力已设计或实现        | 未注册           | 否        |
| 白名单检索    | 后续接入                | 未注册           | 否        |
| 黑名单管理    | 后续接入                | 未注册           | 否        |
| 审批操作     | 后续接入                | 未注册           | 否        |

后端能力、Agent Tool 和本轮动态授权是三个不同层次，文档和代码不得混为一谈。

新增 Agent Tool 时必须同步更新：

* Tool 实现；
* Registry；
* Runner 动态授权；
* Backend Protocol；
* Business Service Adapter；
* Prompt；
* Skill；
* 接口约定；
* 自动化测试；
* 当前能力表。

## 11. Skill 架构

Skill 位于 `skills/` 目录，用于向模型补充可运营的业务规则和话术。

Skill 适合描述：

* 采购需求字段；
* 工具选择指导；
* 追问规则；
* 风险提示；
* 回复格式；
* 合规边界。

Skill 不负责：

* 身份认证；
* 权限控制；
* 工具授权；
* 正式状态机；
* 数据库写入；
* 黑名单硬过滤；
* 幂等和事务。

运行时必须：

1. 创建 `SkillManager`；
2. 显式调用 `load()`；
3. 检查解析错误；
4. 只选择当前允许注入的 Skill；
5. 只注入 `enabled=true` 的 Skill；
6. 限制注入长度。

如果 Runtime 只实例化 `SkillManager` 而未调用 `load()`，Skill 列表为空，Markdown 内容不会自动生效。

Skill 中描述的可执行能力必须与当前 Tool Registry 和动态工具策略一致。

## 12. 会话状态和正式事实

### 12.1 MySQL

MySQL 保存正式业务事实，包括：

* 采购需求编号；
* 申请人；
* 采购字段；
* 正式状态；
* 版本；
* 金额；
* 提交时间；
* 状态历史；
* 审批、采购、交付、验收和入库记录；
* 审计事实。

### 12.2 Redis

Redis 保存短期运行数据，包括：

* 最近聊天消息；
* Agent 短期采购状态；
* 活动采购草稿引用；
* 最近办理草稿引用；
* 聊天请求幂等结果；
* 同一会话的串行锁。

Redis 中的数据不能替代 MySQL 中的采购详情。

在展示、更新、提交、取消或执行其他状态变化前，Agent 应通过工具重新读取后端最新数据。

### 12.3 本地内存 Store

内存 Store 只允许用于：

* 单元测试；
* 明确配置的本地开发；
* 不依赖持久化的受控验证。

生产环境 Redis 不可用时，应安全关闭 Agent 或返回 `AGENT_UNAVAILABLE`，不得静默退化为进程内内存状态。

### 12.4 会话重置

会话重置只清除：

* Redis 聊天历史；
* Redis Agent 短期状态；
* 对应会话缓存。

会话重置不得：

* 删除采购草稿；
* 取消采购申请；
* 修改 MySQL 状态；
* 删除正式审计记录。

## 13. 采购需求数据流

```text
员工描述采购需求
  |
  v
意图识别
  |
  v
Runner 判断当前没有活动草稿
  |
  v
模型调用 create_requirement_draft
  |
  v
RequirementService 创建 MySQL 草稿
  |
  v
返回 requirement_id、requirement_no、version、
missing_fields、conflicts、warnings
  |
  v
模型根据后端结果追问
  |
  v
员工补充或纠正
  |
  v
模型调用 get_requirement_detail
  |
  v
模型调用 update_requirement_draft
  |
  v
Service 校验申请人、状态、version 和幂等
  |
  v
更新 MySQL 并返回最新完整详情
  |
  v
模型说明本轮真实完成内容和剩余事项
```

用户描述另一个采购需求时：

```text
已有活动草稿
  |
  v
模型判断是新需求而非修改
  |
  v
start_new_requirement
  |
  v
创建新草稿
  |
  v
原草稿进入 recent_requirements
  |
  v
新草稿成为活动草稿
```

用户要求切回旧草稿时：

```text
从 recent_requirements 选择目标
  |
  v
switch_active_requirement
  |
  v
后端读取目标草稿
  |
  v
更新短期活动草稿引用
```

## 14. 正式提交和高风险操作

高风险操作的统一链路为：

```text
可信身份
  -> 数据范围
  -> 当前后端状态
  -> 人工明确确认
  -> 动态开放专用工具
  -> 工具参数校验
  -> 幂等检查
  -> version 检查
  -> Business Service 状态转换
  -> 审计记录
  -> 事务提交
  -> 返回新状态
  -> Agent 才能声明成功
```

正式提交、取消、审批、下单、名单生效、验收和入库不得只靠 Prompt 限制。

每个高风险动作应使用独立工具，不能复用普通更新工具间接修改正式状态。

当前尚未注册正式提交和取消工具，因此聊天 Agent 只能读取并展示最新草稿，不能声称已完成提交或取消。

## 15. 推荐数据流

目标推荐链路为：

```text
已确认商品字段
  |
  v
兼容性和生命周期硬约束
  |
  v
有效黑名单过滤
  |
  v
白名单和历史采购召回
  |
  v
确定性评分和排序
  |
  v
保存推荐证据和策略版本
  |
  v
LLM 生成可解释说明
```

LLM 只解释已经由后端确定的候选、匹配依据、历史价格和风险。

LLM 不得：

* 自行生成不存在的供应商；
* 自行改变推荐排名；
* 把历史价格描述为当前报价；
* 将推荐结果自动写入采购草稿；
* 绕过黑名单；
* 把白名单关系解释为普遍强制采购关系。

当前历史供应商推荐尚未注册为 Agent Tool，因此相关 Skill 不能被描述为聊天 Agent 当前已经可执行的能力。

## 16. 一致性、事务和幂等

* 核心业务写操作在单一 MySQL 事务内完成。
* 外部系统采用任务表或 Outbox 风格实现受控最终一致。
* 外部网络调用不得持有长数据库事务。
* 所有写接口接受幂等键。
* 同键同请求返回首次结果。
* 同键不同请求返回 `IDEMPOTENCY_CONFLICT`。
* 状态聚合根使用 `version` 乐观锁。
* 版本不一致返回 `VERSION_CONFLICT`。
* Agent 遇到版本冲突时重新读取最新详情，不得静默覆盖。
* ToolExecutor 的本轮写入指纹只用于防止模型在一次循环中重复调用相同写工具，不能替代业务幂等。
* 高争用数量校验可以使用 `SELECT ... FOR UPDATE`。
* 交付、审批、名单和状态历史采用追加事件。
* 定时任务使用数据库租约或唯一约束防止重复执行。

## 17. 安全

* 身份统一解析为 `CurrentUser`。
* Service 执行组织、楼宇和角色数据范围过滤。
* Agent 请求体不得允许用户指定员工身份、模型 Provider、模型名称或密钥。
* 所有外部输入视为不可信。
* Prompt、Skill 和附件不能覆盖系统权限和工具白名单。
* AgentTool 不接收或持久化原始 Authorization。
* 日志和错误响应不得包含密钥、Token、数据库连接串、SQL 或堆栈。
* 测试数据不得使用真实员工、供应商、报价和合同。
* 生产环境 Redis、模型或业务后端不可用时采用安全失败。
* 不得在工具失败时让模型声称业务操作已经成功。

## 18. 可观测性

统一使用 `request_id` 串联：

```text
HTTP请求
聊天回合
意图识别
模型请求
Tool Call
Business Service
数据库事务
外部系统调用
```

Agent Trace 至少记录：

* `agent.started`；
* 上下文准备完成；
* 当前意图、Scene 和 Stage；
* 本轮开放工具名称；
* 模型请求和完成耗时；
* 工具请求和完成耗时；
* 工具名称；
* 成功或失败；
* 稳定错误码；
* 是否终止；
* 是否达到最大迭代次数。

Trace 不记录：

* 模型隐藏推理；
* Authorization；
* API Key；
* 完整 System Prompt；
* 完整用户消息；
* 完整采购字段值；
* 数据库连接串；
* 无关个人信息。

指标至少覆盖：

* HTTP 延迟和错误率；
* Agent 回合延迟；
* 意图识别延迟；
* 模型延迟和失败率；
* 工具调用次数和失败率；
* 迭代次数；
* Redis 错误和会话锁冲突；
* 数据库耗时；
* 版本冲突；
* 幂等冲突；
* 越权拒绝；
* 审批超时；
* 任务积压。

## 19. 当前实现边界

当前已经具备：

* FastAPI Agent 聊天 API；
* 员工身份隔离；
* 聊天幂等；
* 同一会话串行锁；
* 聊天历史；
* 会话重置；
* Anthropic 模型适配；
* OpenAI 兼容模型适配；
* Tool Calling Runner；
* 动态工具授权；
* 工具参数校验；
* 本轮重复写入阻断；
* 采购草稿创建；
* 采购草稿查询；
* 采购草稿增量修改；
* 同一会话新建另一张草稿；
* 在最近草稿间切换；
* 请求级 Agent Trace；
* CLI 聊天入口。

当前 Agent 仍未开放：

* 正式提交审批工具；
* 取消草稿工具；
* 本人申请列表查询工具；
* 历史供应商推荐工具；
* 白名单和黑名单工具；
* 审批、订单、交付、验收和入库工具。

文档必须明确区分“后端能力已存在”和“Agent 当前已经能够调用”。

## 20. 阶段出口

| 阶段          | 目标                           | 集成出口              |
| ----------- | ---------------------------- | ----------------- |
| M1 工程底座     | 应用、数据库、配置、日志、测试和 CI          | `/health`、空库迁移、CI |
| M2 主数据和权限   | 产品、供应商、名单、历史、身份和审计           | 管理 API 和受控查询      |
| M3 需求 Agent | 聊天会话、意图、Runner、草稿工具、完整性和推荐入口 | 多轮采购草稿            |
| M4 推荐和审批    | 推荐工具、正式提交工具、楼长审批             | 需求到审批通过           |
| M5 采购闭环     | 订单、交付、验收、入库和黑名单治理            | 批准到完成             |
| M6 集成上线     | 飞书、通知、部署和端到端验证               | 内网试运行             |
