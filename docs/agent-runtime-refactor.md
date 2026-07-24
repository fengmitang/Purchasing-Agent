# Agent 内核运行时与路由说明

状态：已落地第一阶段，后续能力仍以当前代码和测试为准。

## 当前调用链

```text
Agent Router
  -> AgentChatService
  -> RouteResolver
  -> AgentService
  -> AgentLoopRuntime
  -> ToolPolicy
  -> ToolExecutor
  -> AgentTool
  -> RequirementBackendProtocol
  -> Business Service
  -> Repository
  -> MySQL
```

## 组件职责

- `RouteResolver` 只负责领域路由：`GENERAL` 或 `PROCUREMENT`。
- `AgentService` 负责加载采购短期状态、生成 `AgentContext` 和调用运行时。
- `AgentLoopRuntime` 负责统一模型—工具循环、最大迭代次数、Trace 和终止保护。
- Procurement 路由向模型提供全部已注册采购 Tool Schema，General 路由不提供采购工具。
- Procurement 路由默认允许全部已注册工具；`ToolPolicy` 仅限制提交、取消、更新三类高风险写操作，模型可见性与执行权限仍然分离。
- `ToolExecutor` 负责工具存在性、参数校验、未授权拦截、重复写拦截和安全错误转换。
- `AgentTool` 只能通过 Backend Protocol 调用 Business Service。
- `AgentDefinition` 组合领域路由、`PromptProvider`、`ToolPolicy` 和可选 Skill 选择器。
- 采购业务 Prompt 已物理迁移到 `app/modules/agent/procurement/prompt.py`；Runtime 只调用 Provider，不再内嵌采购规则或 Skill 拼接逻辑。
- Bootstrap 同时提供 General/Procurement Definition；采购 Skill 使用 `SkillManagerSelector`，General Definition 不开放业务工具。
- `ResponseGuard` 负责拦截模型在没有后端成功结果时的提交/取消成功声明。

旧 `ProcurementAgentRunner` 名称和兼容别名、原 `orchestrator.py` 均已删除；`AgentLoopRuntime` 是唯一主循环。

## 路由与工具授权

`active_route` 属于 ChatStore 的短期会话状态；ChatStore 不再保存采购草稿状态；活动采购草稿属于 ProcurementSessionStore；采购正式字段、状态、版本和审计事实只来自 MySQL。

生产装配中，ChatStore 与 ProcurementSessionStore 共用配置的 Redis 服务但使用独立键空间；两者均为异步实现，键包含组织、员工和会话编号。内存实现仅用于本地和测试。

显式切换到采购或退出采购时，RouteResolver 可以切换领域。进入采购路由后模型可以看到全部已注册采购工具，但不代表获得全部工具执行权限。

General 场景不开放采购业务工具。采购场景默认允许全部已注册工具，仅有三项 Policy 前置限制：提交必须有明确确认，取消必须有明确确认和原因，更新必须存在活动草稿。状态、权限、版本、幂等和数据范围仍由 Agent Tool 与 Business Service 最终校验。

## Memory 与 Knowledge 预留

当前仅提供只读接口：

```python
MemoryProvider.recall(...)
KnowledgeProvider.search(...)
```

空 Provider 不改变当前行为。后续接入时，Memory 和 Knowledge 只能作为模型上下文参考，不得覆盖 MySQL 正式事实、决定权限、改变状态或绕过工具白名单；本阶段不实现自动记忆写入。

Runtime 在每轮开始前执行只读召回；Provider 异常会记录安全日志并降级为空结果，不阻断采购工具循环。召回内容限制长度后才注入 Prompt，并明确标记为非权威参考。

`AgentService.should_handle` 已删除，实际领域路由统一由 `RouteResolver` 负责；路由状态按组织、用户和会话键隔离，重置一个会话不会清除其他会话的路由。

`AgentChatService` 在采购 Intent 识别之前完成领域路由；General 路由不会调用采购 Intent Resolver。不确定的新会话进入无工具安全追问，已有会话默认保持 `active_route`，只有明确切换指令才改变领域。

采购细粒度 Intent 只有一套正式实现：`ModelProcurementIntentResolver`。`IntentCategory` 位于 `enums.py`，原多策略 `intent_recognizer.py` 已删除。

会话重置同时清理 ChatStore 和 ProcurementSessionStore 的短期状态，不影响 MySQL 正式采购事实。

聊天回合采用提交边界：用户和助手消息先写为 `PROCESSING`，Route、ProcurementSessionStore 和聊天幂等结果全部成功后才转为 `COMPLETED`。提交失败时两条消息转为 `FAILED`，并回滚到回合开始前的 Route 和采购 Session，失败消息不参与历史回放。

跨 Store 重置采用幂等、可重试的收敛语义：先清理 ProcurementSessionStore，再清理 ChatStore；任一步失败均返回稳定错误且不写成功幂等结果，使用相同幂等键重试会继续清理直到两个 Store 都为空。CI 使用真实 Redis Service 验证 TTL、序列化、组织隔离和清理。

## 当前未开放能力

- 工作单/告警 Agent；
- 白名单和黑名单 Agent Tool；
- 审批、采购下单、交付、验收和入库 Agent Tool；
- Memory/Knowledge 实际召回和写入。

这些能力必须完成工具注册、动态授权、Backend Protocol、Business Service 校验、审计和测试后，才能标记为 Agent 可执行。

## 验证状态

当前 Agent 改造已通过：

```text
pytest：130 passed, 16 skipped
ruff check：通过
alembic heads：单一 head（0006_workflow_routing）
```

全仓库格式检查仍有两个与本次 Agent 改造无关的既有文件未格式化：`app/modules/requirement/schemas.py` 和 `docs/api-contracts.md`。
