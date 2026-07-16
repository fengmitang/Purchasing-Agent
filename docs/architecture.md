# 系统架构

## 1. 架构目标

项目采用模块化单体：用清晰的模块和契约降低两人并行开发冲突，同时保持一次部署、单一事务边界和轻量运维。首期不使用微服务、Kubernetes、消息队列、独立向量数据库或 Agent 编排框架。

```text
飞书机器人 / Web 管理后台
             |
          FastAPI
             |
  +----------+-----------+
  |          |           |
 Agent    采购业务    权限/审计
  |          |           |
  +----------+-----------+
             |
           MySQL
```

部署单元为 FastAPI 后端、可后置的 React 管理端、MySQL 8.0、Nginx 和定时任务进程，由 Docker Compose 管理。

## 2. 强制分层

```text
Router -> Service -> Repository -> MySQL
AgentService -> AgentHandler -> BusinessService -> Repository -> MySQL
BusinessService -> IntegrationClient -> External System
```

| 层 | 职责 | 禁止 |
| --- | --- | --- |
| Router | HTTP/回调协议、输入解析、依赖注入、响应映射 | ORM 查询、业务授权、事务提交 |
| Service | 权限、数据范围、规则、状态机、事务、幂等、审计 | 返回 ORM 实体、绕过契约 |
| Repository | 查询、持久化、锁和分页 | 决定权限、审批或业务状态 |
| Agent Handler | Scene/Stage 路由、抽取、追问和回复编排 | 直接访问数据库、执行高风险写入 |
| Integration Client | 外部协议、签名、超时、重试和响应转换 | 承担业务决策 |

## 3. 模块边界

| 模块 | 负责 | 不负责 | 主责 |
| --- | --- | --- | --- |
| `agent` | 场景识别、字段抽取、追问、会话阶段 | 正式状态和数据库直写 | A |
| `requirement` | 草稿、需求单、明细、版本、状态历史 | 产品评分 | A |
| `product` | 分类、品牌、型号、规格、生命周期、替代 | 审批 | B |
| `supplier` | 供应商、产品关系、履约指标 | 名单生效决策 | B |
| `whitelist` | 范围、版本、有效期和查询 | 自然语言推荐 | B |
| `blacklist` | 对象、证据、复核、生效、失效 | 让 LLM 直接生效 | B（自然语言草稿 A 协作） |
| `recommendation` | 硬过滤、召回、评分、排序和快照 | 创建采购单 | B |
| `approval` | 实例、任务、记录、权限和动作 | 操作订单明细 | B |
| `purchase` | 询价、订单、供应商选择和变更 | 直接入库 | B |
| `delivery` | 追加式交付事件和延期指标 | 覆盖订单事实 | B |
| `inspection` | 验收、质量异常、拒收和退换货 | 修改名单 | B |
| `inbound` | 入库单、明细、数量幂等和外部同步 | 绕过验收 | B |
| `audit` | 操作、状态和模型调用留痕 | 承载业务主数据 | A（共同使用） |
| `shared` | 公共契约、异常、身份、分页和时钟 | 业务模块特有规则 | A/共同审查 |

跨模块调用只能依赖公开 Service Protocol 和 Pydantic Schema，不允许模块读取另一个模块的 Repository。

## 4. 推荐目录

```text
app/
  main.py
  bootstrap.py
  config.py
  api/
  agent/
    handlers/
    extractors/
  modules/
    requirement/ product/ supplier/ whitelist/ blacklist/
    recommendation/ approval/ purchase/ delivery/ inspection/ inbound/ audit/
  integrations/
    feishu/ llm/ storage/
  infrastructure/
    database/ logging/ tasks/
  shared/
migrations/
tests/
  unit/ integration/ api/ agent/
```

每个业务模块内部按需包含 `router.py`、`service.py`、`repository.py`、`models.py`、`schemas.py`、`enums.py`；不要为尚未开发的模块批量生成空壳。

## 5. 关键数据流

### 5.1 需求和推荐

1. Router/飞书 Client 验证身份、验签和幂等键。
2. AgentService 加载会话，Handler 抽取字段并通过确定性合并更新草稿。
3. CompletenessChecker 根据品类模板返回缺失/冲突字段。
4. 信息完整后调用 RecommendationService。
5. Service 执行兼容性硬约束、黑名单过滤、白名单/历史召回和确定性评分。
6. 保存候选、规则版本、证据引用和评分快照后，LLM 只生成解释。
7. 用户确认时 RequirementService 在事务内创建正式版本并提交审批。

### 5.2 高风险写操作

```text
身份/数据范围 -> 当前状态 -> 明确确认 -> 幂等检查
-> 业务写入/状态转换 -> 审计记录 -> 事务提交 -> 通知任务
```

通知使用 MySQL 任务表/outbox 风格记录，避免数据库已提交但通知丢失。外部调用不得持有长数据库事务。

### 5.3 交付和入库

交付、状态历史、审批记录和名单历史均采用追加事件。入库 Service 锁定订单明细或检查 `version`，计算已入库量与可入库余额，超量立即阻断。

## 6. Agent 架构

首期使用有限状态 Agent：

- Scene：`GENERAL_QUERY`、`PROCUREMENT_REQUIREMENT`、`PROCUREMENT_STATUS`、`BLACKLIST`、`WHITELIST_QUERY`、`SUPPLIER_QUERY`。
- Stage：`INTENT_RECOGNITION`、`COLLECTING_INFORMATION`、`WAITING_FOR_CLARIFICATION`、`PRODUCT_SEARCH`、`WAITING_FOR_PRODUCT_SELECTION`、`WAITING_FOR_CONFIRMATION`、`SUBMITTED`、`COMPLETED`、`CANCELLED`。
- 主循环只负责加载上下文、解析 Handler、执行、持久化和返回。
- 所有 LLMClient 实现置于统一抽象后，带超时、有限重试、结构化校验、脱敏和调用审计。

## 7. 一致性、幂等与任务

- 核心写操作在单一 MySQL 事务内完成；跨外部系统采用任务表和受控最终一致。
- 回调、创建订单、审批、交付事件和入库必须接受幂等键；同键同载荷返回原结果，不同载荷返回冲突。
- 对状态聚合根使用 `version` 乐观锁；高争用数量校验可使用 `SELECT ... FOR UPDATE`。
- 定时任务通过数据库租约/唯一约束防止重复执行；失败记录次数、下次执行时间和最后错误。

## 8. 安全与可观测性

- 身份解析为 `CurrentUser`，Service 接收 `UserDataScope` 并执行组织/楼宇过滤。
- 所有外部输入视为不可信；附件内容不能覆盖系统 Prompt 或授权规则。
- 日志使用 `request_id`/`trace_id` 串联 API、数据库、任务和模型调用，并脱敏密钥与个人信息。
- 指标至少覆盖请求延迟/错误、数据库耗时、LLM 延迟/失败、任务积压、审批超时、幂等冲突和越权拒绝。

## 9. 阶段出口

| 阶段 | 集成出口 |
| --- | --- |
| M1 工程底座 | 应用启动、`/health`、空库迁移、Ruff/Pytest/CI |
| M2 主数据和名单 | 管理 API、有效期/范围查询、导入、权限和审计 |
| M3 需求 Agent | 多轮草稿、品类完整性、联合检索入口 |
| M4 推荐和审批 | 需求到审批通过闭环 |
| M5 采购闭环 | 订单到验收入库、黑名单治理 |
| M6 飞书和上线 | 验签去重、卡片、通知、端到端试运行 |
