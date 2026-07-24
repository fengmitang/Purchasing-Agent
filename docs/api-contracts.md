# API 与模块契约

> 本文记录公开契约。状态为 `Planned` 的接口用于约束开发顺序，不代表已经实现。

Agent 创建采购草稿、历史供应商推荐和员工确认提交的详细协作契约见
[`agent-backend-interface-agreement.md`](agent-backend-interface-agreement.md)。若概述与详细契约存在歧义，开发前必须由双方共同确认并同步修正文档。

## 1. 通用约定

- API 前缀：`/api/v1`；健康检查为 `/health`。
- JSON 字段使用 `snake_case`；时间为带时区 ISO 8601；数据库统一 UTC。
- 金额和数量通过 JSON 字符串传输；采购申请数量必须是大于 0 的整数，金额由服务端使用 `Decimal` 处理，禁止浮点数。
- 所有写接口接受 `Idempotency-Key`；请求可携带 `X-Request-ID`，服务端校验后沿用或生成新值，并在同名响应头、响应体和日志中返回。
- 列表默认分页，禁止无上限返回；稳定排序必须包含唯一键作为次排序。
- 网页使用后端服务端会话生成 `CurrentUser`；本地自动化测试可按配置使用临时身份请求头，生产环境强制关闭。未来 SSO 只替换身份适配器，不改变 Service 契约。关键接口在身份源不可用时拒绝匿名执行。

### 1.1 成功和错误

单对象响应：

```json
{
  "data": {},
  "meta": {"request_id": "..."}
}
```

错误响应：

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "面向用户的安全说明",
    "details": [],
    "request_id": "..."
  }
}
```

错误码稳定且不暴露堆栈、SQL、密钥或内部连接信息。基础错误：`VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`RESOURCE_NOT_FOUND`、`STATE_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`VERSION_CONFLICT`、`RATE_LIMITED`、`INTERNAL_ERROR`。采购需求流程补充使用 `EMPLOYEE_NOT_MAPPED`、`REQUIREMENT_INCOMPLETE` 和 `BLACKLIST_BLOCKED`。

参数验证错误返回 422 `VALIDATION_ERROR`；未处理异常返回 500 `INTERNAL_ERROR` 和固定安全说明。错误响应不得回显被拒绝的原始输入。`X-Request-ID` 只接受 1–128 位字母、数字、点、下划线、冒号或连字符，缺失或不合法时由服务端重新生成。

分页响应：

```json
{
  "data": [],
  "page": {"number": 1, "size": 20, "total": 0},
  "meta": {"request_id": "..."}
}
```

`page_size` 默认 20，最大 100。

## 2. 公共类型

```python
class CurrentUser(BaseModel):
    user_id: int
    user_code: str
    roles: frozenset[str]
    organization_id: int
    building_ids: frozenset[int]


class UserDataScope(BaseModel):
    organization_ids: frozenset[int]
    building_ids: frozenset[int]
    category_ids: frozenset[int]
    global_access: bool = False


class AuditContext(BaseModel):
    actor: CurrentUser
    request_id: str
    idempotency_key: str | None = None
    reason: str | None = None
    source_ip: str | None = None


class PageRequest(BaseModel):
    page: int = 1
    page_size: int = 20
    sort: tuple[str, ...] = ()
```

所有 Service 写方法显式接收 `AuditContext`；需要数据过滤的方法显式接收 `UserDataScope`，不得从全局变量隐式获取。

## 3. M1 接口

| 状态 | 方法与路径 | 用途 | 验收 |
| --- | --- | --- | --- |
| Implemented | `GET /health` | 进程存活，不依赖外部系统 | 返回 200、服务状态、服务名、版本和 UTC 时间 |
| Planned | `GET /api/v1/health/ready` | 检查数据库和迁移就绪 | 依赖失败返回 503，不泄密 |
| Implemented | `POST /api/v1/auth/login` | 使用员工工号或电话和密码登录 | 成功设置 HttpOnly 会话 Cookie |
| Implemented | `GET /api/v1/auth/me` | 返回当前员工、角色和楼宇范围 | 未认证 401 |
| Implemented | `POST /api/v1/auth/logout` | 撤销服务端会话并清除 Cookie | 可重复调用 |
| Implemented | `POST /api/v1/auth/change-password` | 修改本人密码并撤销全部会话 | 校验当前密码和新密码强度 |

### 3.1 登录与当前用户

- 登录请求体为 `identifier` 和 `password`，`identifier` 可以是员工工号或已登记联系电话；
- 登录失败统一返回“工号、电话或密码不正确”，不得暴露账号是否存在、被禁用或被锁定；
- 连续失败 5 次临时锁定 15 分钟，成功登录后清零；
- 会话原始令牌只放在安全 Cookie 中，数据库只保存 SHA-256 摘要；
- `GET /api/v1/auth/me` 返回 `employee_no`、姓名、电话、角色和楼宇范围；当前版本不强制首次登录修改密码；
- 密码修改成功后全部会话失效，员工必须使用新密码重新登录。

### 3.2 `GET /health`

健康检查直接返回以下响应，不套用通用 `data`/`meta` 包装：

```json
{
  "status": "ok",
  "service": "purchasing-agent",
  "version": "0.1.0",
  "time": "2026-07-17T01:21:38.779939Z"
}
```

- `status` 固定为 `ok`；
- `service` 为服务名；
- `version` 为当前应用版本；
- `time` 为带时区的 UTC ISO 8601 时间；
- 该接口只表示应用进程存活，不访问数据库或其他外部系统。
- 该接口的响应体不套用通用信封，但仍在 `X-Request-ID` 响应头中返回请求 ID。

## 4. M2 HTTP 接口

### 4.0 审批与采购执行

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Implemented | `GET /api/v1/buildings` | 查询员工申请时可选择的有效楼宇 |
| Implemented | `GET /api/v1/approvals/tasks` | 楼长查询职责楼宇内的待审批申请 |
| Implemented | `GET /api/v1/approvals/tasks/{requirement_id}` | 楼长查看完整审批详情 |
| Implemented | `POST /api/v1/approvals/tasks/{requirement_id}/decision` | 楼长通过或驳回申请，禁止自审 |
| Implemented | `POST /api/v1/purchase-requirements/{requirement_id}/revise` | 员工基于被驳回申请创建修改草稿 |
| Implemented | `GET /api/v1/procurement/tasks` | 采购员查看审批通过及采购中的任务 |
| Implemented | `POST /api/v1/procurement/requirements/{requirement_id}/start` | 领取任务并开始采购 |
| Implemented | `POST /api/v1/procurement/orders/{order_id}/advance` | 记录询价核价或合同签订状态 |
| Implemented | `POST /api/v1/procurement/orders/{order_id}/complete` | 记录验收入库时间并完成采购 |

楼长任务由 `PENDING_APPROVAL + building_id + 当前楼长有效楼宇职责` 实时计算。审批通过后申请状态
变为 `APPROVED` 并进入采购员队列；采购完成必须同时记录 `received_at`、`completed_at`、采购人员
工号、姓名和联系方式快照。所有状态写入均校验角色、数据范围、状态、版本和幂等键。

### 4.1 产品与供应商

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Planned | `GET /api/v1/products` | 按分类、名称、品牌、型号、生命周期和状态分页查询 |
| Planned | `POST /api/v1/products` | 管理员创建产品；业务唯一键冲突返回 409 |
| Planned | `GET /api/v1/products/{product_id}` | 返回产品、规格和有效供应商关系 |
| Planned | `PATCH /api/v1/products/{product_id}` | 带 `version` 更新；生命周期变化审计 |
| Planned | `GET /api/v1/suppliers` | 按名称、编码、状态分页查询 |
| Planned | `POST /api/v1/suppliers` | 管理员创建供应商 |
| Planned | `PATCH /api/v1/suppliers/{supplier_id}` | 带 `version` 更新 |
| Planned | `PUT /api/v1/products/{product_id}/suppliers/{supplier_id}` | 创建/更新有期限的产品供应商关系 |

写接口仅允许主数据管理员，查询由 `UserDataScope` 过滤。

### 4.2 白名单和黑名单

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Planned | `GET /api/v1/whitelists` | 默认只返回当前有效且在数据范围内的条目 |
| Planned | `POST /api/v1/whitelists` | 授权管理员创建版本化条目 |
| Planned | `PATCH /api/v1/whitelists/{id}` | 带版本更新/失效并追加历史 |
| Planned | `GET /api/v1/blacklists` | 按对象、范围、状态和有效期查询 |
| Planned | `POST /api/v1/blacklists` | 创建 DRAFT；不得直接 ACTIVE |
| Planned | `POST /api/v1/blacklists/{id}/submit` | 发起人确认并提交独立复核 |
| Planned | `POST /api/v1/blacklists/{id}/review` | 非发起人复核为 ACTIVE/REJECTED |
| Planned | `POST /api/v1/blacklists/{id}/release` | 采购管理员解除并提供理由 |

有效黑名单查询结果永远优先于白名单。MVP 不提供例外采购接口。

### 4.3 历史数据与导入

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Planned | `GET /api/v1/purchase-history` | 按产品、供应商、组织、楼宇和日期分页查询 |
| Planned | `POST /api/v1/imports/whitelists` | 上传并创建异步校验任务，不直接写正式数据 |
| Planned | `GET /api/v1/imports/{job_id}` | 返回总数、有效、错误、重复和状态 |
| Planned | `POST /api/v1/imports/{job_id}/commit` | 明确确认后幂等写入合法行 |

上传限制文件类型、大小和权限；解析错误必须包含行号/字段，但不得回显敏感整行。

### 4.4 审计

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Planned | `GET /api/v1/audit-logs` | 仅审计角色，按对象、操作人、动作和时间分页查询 |
| Planned | `GET /api/v1/audit-logs/{id}` | 返回前后值、理由、请求和关联对象 |

审计写入不作为公共 Router 暴露，只能由业务 Service 调用 AuditService。

## 5. M1/M2 Service Protocol

```python
class ProductQueryServiceProtocol(Protocol):
    async def search(
        self, query: ProductSearch, scope: UserDataScope, page: PageRequest
    ) -> Page[ProductSummary]: ...


class WhitelistServiceProtocol(Protocol):
    async def find_effective(
        self, query: WhitelistQuery, scope: UserDataScope, at: datetime
    ) -> tuple[WhitelistMatch, ...]: ...


class BlacklistServiceProtocol(Protocol):
    async def find_effective(
        self, query: BlacklistQuery, scope: UserDataScope, at: datetime
    ) -> tuple[BlacklistMatch, ...]: ...


class PurchaseHistoryServiceProtocol(Protocol):
    async def search_similar(
        self, query: HistoryQuery, scope: UserDataScope, page: PageRequest
    ) -> Page[PurchaseHistorySummary]: ...


class AuditServiceProtocol(Protocol):
    async def record(self, event: AuditEvent, context: AuditContext) -> None: ...
```

RecommendationService 只能使用以上公开查询契约；不得直接引用名单或历史 Repository。

## 6. 后续业务契约边界

- `RequirementService.submit`：按登录账号自动确定所属楼宇，校验申请原因、具体申请地点、设备名称和数量，
  保存版本和推荐快照引用，幂等提交审批；申请类别不再由员工填写，其他采购字段允许留空。
- `ApprovalService.act`：验证任务归属、楼宇范围、禁止自审和当前状态，追加审批记录。
- `PurchaseService.create_order`：仅接受已批准需求，一个需求只生成一个活动采购任务。
- `DeliveryService.append_event`：只追加事件，不覆盖历史。
- `InboundService.receive`：校验验收结论与剩余数量，锁/版本控制并幂等入库。
- `BlacklistService.activate`：只能由复核动作触发；Agent 只创建草稿。

公共 Schema、枚举或错误码的任何不兼容变化必须先更新本文，并在 PR 中单独列出。

## 7. 回调与幂等语义

- 外部回调先验签，再以平台事件 ID 去重；验签失败不得进入业务层。
- 同一幂等键和同一请求哈希返回首次结果；同键不同请求返回 `IDEMPOTENCY_CONFLICT`。
- 事务提交后再确认处理成功；通知失败进入任务表重试，不回滚已经完成的业务事实。
- 乐观锁冲突返回 409 `VERSION_CONFLICT`，客户端重新读取后决定是否重试。

## 8. 内部员工 Agent 聊天 API

聊天接口仅接受可信代理提供的员工身份。聊天历史和 Agent 会话状态保存在 Redis，
不得替代 MySQL 中的正式采购事实。

| 状态 | 方法与路径 | 说明 |
| --- | --- | --- |
| Implemented | `POST /api/v1/agent/messages` | 同步处理一条文本消息；写请求要求 `Idempotency-Key` |
| Implemented | `GET /api/v1/agent/conversations/{conversation_id}/messages` | 分页读取当前员工所属会话历史 |
| Implemented | `DELETE /api/v1/agent/conversations/{conversation_id}` | 清除短期会话，不删除采购事实；要求 `Idempotency-Key` |

`POST /api/v1/agent/messages` 请求：

```json
{
  "conversation_id": "conv-001",
  "client_message_id": "web-0001",
  "content": "我要采购两台服务器"
}
```

`conversation_id` 和 `client_message_id` 只接受 1～100 位字母、数字、点、下划线或连字符；
`content` 为 1～10000 字符文本。客户端不得指定 Provider、模型、身份或密钥。

成功响应的 `data` 包含 `message_id`、`conversation_id`、`role`、`content`、`intent`、
`scene`、`stage`、可空 `active_requirement` 和 UTC `created_at`。不得返回模型推理、
原始 Tool Call、Trace 或凭证。

历史接口使用通用分页信封，默认 `page=1`、`page_size=20`、最大 100；只返回
`USER`/`ASSISTANT` 文本、处理状态和时间。删除接口返回 `cleared=true`。

新增稳定错误码：

- 503 `AGENT_UNAVAILABLE`：模型、Redis 或 Agent 配置不可用；
- 409 `CONVERSATION_BUSY`：同一会话无法在等待时间内取得串行锁。

同一幂等键与相同请求哈希返回首次结果；同键不同请求返回
`IDEMPOTENCY_CONFLICT`。会话键由服务端按
`organization_id:user_code:conversation_id` 生成，禁止跨员工读取或清除。
