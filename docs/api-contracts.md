# API 与模块契约

> 本文记录公开契约。状态为 `Planned` 的接口用于约束开发顺序，不代表已经实现。

## 1. 通用约定

- API 前缀：`/api/v1`；健康检查为 `/health`。
- JSON 字段使用 `snake_case`；时间为带时区 ISO 8601；数据库统一 UTC。
- 金额和精确数量通过 JSON 字符串传输，服务端使用 `Decimal`，禁止浮点数。
- 所有写接口接受 `Idempotency-Key`；外部请求携带/生成 `X-Request-ID`。
- 列表默认分页，禁止无上限返回；稳定排序必须包含唯一键作为次排序。
- M1/M2 使用内部身份适配器生成 `CurrentUser`；未来 SSO 只替换适配器，不改变 Service 契约。关键接口在身份源不可用时拒绝匿名执行。

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

错误码稳定且不暴露堆栈、SQL、密钥或内部连接信息。基础错误：`VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`RESOURCE_NOT_FOUND`、`STATE_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`VERSION_CONFLICT`、`RATE_LIMITED`、`INTERNAL_ERROR`。

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
| Planned | `GET /health` | 进程存活，不依赖外部系统 | 返回 200 和版本/时间 |
| Planned | `GET /api/v1/health/ready` | 检查数据库和迁移就绪 | 依赖失败返回 503，不泄密 |
| Planned | `GET /api/v1/me` | 返回当前用户、角色和数据范围 | 未认证 401 |

## 4. M2 HTTP 接口

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

- `RequirementService.submit`：完成必填/冲突/名单校验，保存版本和推荐快照引用，幂等提交审批。
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
