# Agent 与采购业务后端接口约定

> 状态：M3/M4 开发约定 v1.0
>
> 适用范围：采购需求草稿、员工确认提交、历史采购与供应商推荐
>
> 契约维护：Agent 开发者与采购业务后端开发者共同审查

## 1. 文档目的

本文是 Agent 模块与采购业务后端之间的协作契约，明确双方各自负责的代码、可以调用的接口、请求和响应格式以及完整调用顺序。

本文约定的是业务语义。当前模块化单体中，Agent Handler 应通过公开 Business Service 调用后端；如果 Agent 独立部署或由 Web/飞书端调用，则使用本文对应的 HTTP API。两种调用方式的字段、校验和错误语义必须一致。

数据库字段和表结构以 `docs/database-design-2.md` 为准，公共响应、幂等、分页和错误格式以 `docs/api-contracts.md` 为准。

## 2. 已确认的业务规则

1. Agent 只帮助员工创建和修改采购草稿，不能替员工自动提交审批。
2. 员工必须看到完整采购单并执行一次明确的人工确认，后端才允许把草稿提交审批。
3. 员工输入商品后，系统查询相似的历史已完成采购记录，并推荐以前采购该商品时使用过的供应商。
4. 推荐是参考信息，不是强制选择，不得自动覆盖员工已经填写的商品、供应商或价格。
5. 员工可以购买主数据中尚不存在的商品，也可以为已有商品选择新的供应商。
6. `product_id` 和 `supplier_id` 都允许为空；申请单始终保存员工确认时的商品、供应商文本快照。
7. `product_supplier` 只表示已维护的商品—供应商关系，不是员工创建采购草稿的准入限制。
8. 历史价格必须标明采购日期和币种，只能作为历史参考价，不能表述为当前报价。
9. 后端是采购单、状态和权限的唯一事实来源；Agent 不直接访问 MySQL，不自行生成正式状态或单号。

## 3. 双方职责

### 3.1 Agent 端负责

Agent 开发者需要实现：

- 识别“新建采购需求、继续补充、修改草稿、查看草稿、确认提交、查询状态”等意图；
- 从自然语言中提取本文规定的草稿字段，未知信息传 `null`，不得编造；
- 根据后端返回的 `missing_fields` 和 `conflicts` 进行针对性追问；
- 调用历史供应商推荐接口，并把来源采购单、历史价格和时间展示给员工；
- 明确区分“Agent 推荐内容”和“员工当前选择”；
- 在提交前调用详情接口，向员工展示完整采购单；
- 只有在员工明确点击或表达“确认提交审批”后，才调用提交接口；
- 使用后端返回的 `requirement_id`、`requirement_no`、`status`、`version`，不得自行伪造；
- 根据稳定错误码决定继续追问、提示重新加载或停止提交。

Agent 端不得：

- 直接查询或写入数据库；
- 自动把新供应商写入正式供应商主数据；
- 因为商品—供应商关系不存在而拒绝创建草稿；
- 自行计算并写死总价、审批人或申请人信息；
- 在未获得员工明确确认时调用提交审批接口；
- 根据 LLM 判断绕过黑名单、权限、状态机或后端校验。

### 3.2 采购业务后端负责

后端开发者需要实现：

- 从认证上下文识别当前员工并校验数据范围；
- 创建、读取和增量修改采购草稿；
- 生成唯一的 `requirement_id` 和 `requirement_no`；
- 返回缺失字段、冲突字段、主数据匹配和名单提示；
- 查询相似历史采购单并生成可追溯的供应商推荐；
- 支持 `product_id = null` 或 `supplier_id = null` 的新增商品/供应商场景；
- 提交时重新校验必填字段、状态、权限、版本和幂等键；
- 使用 `Decimal` 计算金额，并保存申请人、商品和供应商快照；
- 在同一事务中更新状态、提交时间并追加状态历史和审计记录；
- 返回稳定、安全、可供 Agent 判断的错误码。

后端不得：

- 信任 Agent 传入的员工姓名、电话、总价、状态或审批人；
- 将历史推荐结果自动写成员工最终选择；
- 把“不在 `product_supplier` 中”当作创建草稿失败；
- 在草稿创建或修改时自动提交审批；
- 向 Agent 返回 SQL、连接串、堆栈或无关员工的个人信息。

## 4. 身份、通用格式与调用约定

### 4.1 员工身份

- 正式调用中，员工身份来自登录态对应的 `CurrentUser`，后端用 `CurrentUser.user_code` 映射 `employee.employee_no`。
- Agent 请求体不传 `employee_no`、员工姓名或联系电话，避免冒用其他员工身份。
- 后端创建草稿时写入 `employee_id`；员工确认提交时保存 `applicant_employee_no`、`applicant_name` 和 `applicant_phone` 快照。
- 本地联调可由身份适配器固定模拟员工，但仍通过认证上下文注入，不在业务请求中临时传工号。

### 4.2 通用协议

- API 前缀：`/api/v1`。
- JSON 字段：`snake_case`。
- 时间：带时区 ISO 8601；数据库按 UTC 保存。
- 金额和数量：JSON 字符串，例如数量 `"2"`、金额 `"35000.00"`；采购申请数量必须是大于 0 的整数，禁止 JSON 浮点数。
- 所有写接口必须携带 `Idempotency-Key`。
- 客户端可以携带 `X-Request-ID`；后端在响应头和响应体中返回最终请求 ID。
- 修改和提交必须携带当前 `version`，发生并发修改时返回 409 `VERSION_CONFLICT`。

成功响应：

```json
{
  "data": {},
  "meta": {
    "request_id": "req-20260721-001"
  }
}
```

错误响应：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "采购数量必须大于 0",
    "details": [
      {"field": "quantity", "reason": "must_be_positive"}
    ],
    "request_id": "req-20260721-001"
  }
}
```

## 5. 共同数据结构

### 5.1 `RequirementDraftInput`

创建草稿时可以只传已经识别出的字段；修改草稿时只传发生变化的字段。
`building_id` 不由 Agent 或前端传入，后端根据当前登录账号关联的唯一有效楼宇自动写入。

| 字段 | 类型 | 草稿 | 提交审批 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | string/null | 可选 | 可选 | 来源 Agent 会话编号 |
| `category_id` | integer/null | 可选 | 可选 | 匹配到的产品分类 ID |
| `category_name` | string/null | 可选 | 可选 | 兼容历史数据；新建申请无需填写 |
| `application_reason` | string/null | 可选 | 必填 | 采购原因 |
| `application_location` | string/null | 可选 | 必填 | 使用或申请地点 |
| `device_type` | string/null | 可选 | 可选 | 设备类型 |
| `product_id` | integer/null | 可选 | 可选 | 匹配到的白名单/产品主数据 ID |
| `product_name` | string/null | 可选 | 必填 | 设备名称 |
| `product_full_name` | string/null | 可选 | 可选 | 具体设备全称 |
| `brand` | string/null | 可选 | 可选 | 品牌 |
| `model` | string/null | 可选 | 可选 | 型号 |
| `specification` | string/null | 可选 | 可选 | 规格参数 |
| `quantity` | integer string/null | 可选 | 必填 | 必须是大于 0 的整数 |
| `unit` | string/null | 可选 | 可选 | 台、个、套等 |
| `supplier_id` | integer/null | 可选 | 可选 | 匹配到的正式供应商 ID |
| `supplier_name` | string/null | 可选 | 可选 | 供应商名称 |
| `unit_price` | decimal string/null | 可选 | 可选 | 预算/参考单价，不等同采购报价 |
| `currency` | string | 可选 | 可选 | 默认 `CNY` |

规则：

- 如果只有 `product_id`，后端仍应返回对应商品快照供员工确认；提交时后端以员工最终确认的快照为准。
- 如果 `product_id` 为空，只要商品必填文本完整，允许提交并标记 `new_product = true`。
- 如果 `supplier_id` 为空但填写了 `supplier_name`，允许保存和提交，并标记 `new_supplier = true`。
- 如果员工尚未选择供应商或参考单价，相关字段可为空，不妨碍创建草稿或正式提交。
- `total_amount` 不作为输入字段。`quantity` 和 `unit_price` 均存在时由后端计算，否则返回 `null`。

### 5.2 `RequirementDetail`

```json
{
  "requirement_id": 501,
  "requirement_no": "PR-20260721-0501",
  "status": "DRAFT",
  "version": 3,
  "applicant": {
    "employee_no": "E20260001",
    "name": "示例员工",
    "phone": "已脱敏或按权限返回"
  },
  "session_id": "session-001",
  "category_id": 2,
  "category_name": "算力服务器",
  "application_reason": "测试环境计算资源不足",
  "application_location": "A区数据中心3楼",
  "device_type": "服务器",
  "product_id": 18,
  "product_name": "机架式服务器",
  "product_full_name": "双路2U机架式服务器",
  "brand": "示例品牌",
  "model": "DEV-MODEL-001",
  "specification": "双路处理器，2U",
  "quantity": "2",
  "unit": "台",
  "supplier_id": null,
  "supplier_name": "员工填写的新供应商",
  "unit_price": "35000.00",
  "total_amount": "70000.00",
  "currency": "CNY",
  "new_product": false,
  "new_supplier": true,
  "missing_fields": [],
  "conflicts": [],
  "warnings": [
    {
      "code": "SUPPLIER_NOT_IN_MASTER_DATA",
      "message": "该供应商尚未进入供应商主数据，提交后由采购人员核实。"
    }
  ],
  "requested_at": "2026-07-21T06:20:00Z",
  "submitted_at": null,
  "updated_at": "2026-07-21T06:35:00Z"
}
```

`requested_at` 表示员工首次发起本次采购需求的时间；`submitted_at` 只在员工确认提交审批后写入。

## 6. 后端需要实现的 HTTP 接口

### 6.1 接口总表

| 状态 | 方法与路径 | 功能 | Agent 如何使用 |
| --- | --- | --- | --- |
| Implemented | `POST /api/v1/purchase-requirements/drafts` | 创建采购草稿 | 首次识别到采购意图并取得至少一个有效业务字段后调用一次 |
| Implemented | `GET /api/v1/purchase-requirements/{id}` | 获取完整采购单 | 恢复会话、展示确认页和提交成功后刷新状态时调用 |
| Implemented | `PATCH /api/v1/purchase-requirements/{id}` | 增量修改草稿 | 每轮补充或员工纠正字段后调用；不要重复创建草稿 |
| Implemented | `POST /api/v1/purchase-requirements/{id}/submit` | 员工确认后提交审批 | 仅在明确人工确认后调用 |
| Implemented | `POST /api/v1/purchase-requirements/{id}/cancel` | 取消未审批草稿 | 员工明确取消时调用 |
| Implemented | `GET /api/v1/purchase-requirements` | 查询本人采购申请 | 状态查询或找回历史草稿时调用，必须分页 |
| Implemented（名单过滤待名单模块接入） | `POST /api/v1/recommendations/historical-suppliers/search` | 查询相似历史采购和供应商 | 商品信息足以检索时调用；结果仅供参考 |

### 6.2 创建草稿

`POST /api/v1/purchase-requirements/drafts`

请求头：

```text
Idempotency-Key: draft-session-001-create
X-Request-ID: req-20260721-001
```

请求：

```json
{
  "session_id": "session-001",
  "category_name": "算力服务器",
  "application_reason": "测试环境计算资源不足",
  "device_type": "服务器",
  "product_name": "机架式服务器",
  "brand": "示例品牌",
  "quantity": "2",
  "unit": "台",
  "currency": "CNY"
}
```

响应 `201 Created`：返回完整 `RequirementDetail`。草稿信息不完整时仍可创建，并通过 `missing_fields` 告知 Agent 下一步追问项。

幂等规则：同一员工、同一 `Idempotency-Key`、同一请求内容重复调用，返回首次创建的草稿；同键不同内容返回 409 `IDEMPOTENCY_CONFLICT`。

### 6.3 获取采购单详情

`GET /api/v1/purchase-requirements/{requirement_id}`

响应 `200 OK`：返回完整 `RequirementDetail`。普通员工只能读取本人申请；审批人和采购人员按角色及楼宇数据范围读取。

Agent 在向员工展示提交确认内容前必须重新读取，不能只展示会话内缓存。

### 6.4 修改草稿

`PATCH /api/v1/purchase-requirements/{requirement_id}`

请求：

```json
{
  "version": 3,
  "application_location": "A区数据中心3楼",
  "model": "DEV-MODEL-001",
  "supplier_id": null,
  "supplier_name": "员工填写的新供应商",
  "unit_price": "35000.00"
}
```

响应 `200 OK`：返回更新后的完整 `RequirementDetail`。

规则：

- 只允许申请人修改本人的 `DRAFT` 草稿；
- 请求只包含本次确认变化的字段；未出现的字段保持不变；
- 需要清空字段时显式传 `null`；
- `status`、`total_amount`、申请人快照和审批字段不允许由客户端修改；
- 版本不一致返回 409 `VERSION_CONFLICT`，Agent 重新读取后让员工确认，不得静默覆盖。

### 6.5 查询历史供应商推荐

`POST /api/v1/recommendations/historical-suppliers/search`

这是只读搜索，不会修改草稿，也不会自动选择供应商。

请求：

```json
{
  "requirement_id": 501,
  "product_id": 18,
  "device_type": "服务器",
  "product_name": "机架式服务器",
  "product_full_name": "双路2U机架式服务器",
  "brand": "示例品牌",
  "model": "DEV-MODEL-001",
  "specification": "双路处理器，2U",
  "application_location": "A区数据中心3楼",
  "limit": 5
}
```

除 `requirement_id` 外，Agent 传入已经确认的商品字段；未知字段传 `null`。`limit` 默认 5，最大 20。

响应：

```json
{
  "data": {
    "query_summary": "机架式服务器 / 示例品牌 / DEV-MODEL-001",
    "recommendations": [
      {
        "rank": 1,
        "match_score": "0.9200",
        "matched_fields": ["product_name", "brand", "model"],
        "supplier_id": 12,
        "supplier_name": "历史测试供应商有限公司",
        "historical_order_count": 4,
        "latest_purchase": {
          "requirement_id": 86,
          "requirement_no": "PR-20260318-0086",
          "order_id": 31,
          "order_no": "PO-20260320-0031",
          "product_name": "双路2U机架式服务器",
          "brand": "示例品牌",
          "model": "DEV-MODEL-001",
          "quantity": "2.0000",
          "unit": "台",
          "unit_price": "34800.00",
          "currency": "CNY",
          "purchased_at": "2026-03-20T02:20:00Z",
          "received_at": "2026-04-02T08:30:00Z",
          "status": "COMPLETED"
        },
        "reason": "品牌和型号相同，该供应商有 4 次已完成采购记录。",
        "warnings": ["历史价格仅供参考，不代表当前报价。"]
      }
    ]
  },
  "meta": {
    "request_id": "req-20260721-002"
  }
}
```

推荐规则：

- 优先使用已完成且有可追溯供应商快照的历史采购单；
- 优先级为型号完全匹配、品牌与商品名称匹配、设备类型匹配、时间较近；
- 同一供应商的多条历史记录聚合展示，并提供最近一次采购单引用；
- 结果必须受当前员工的数据范围约束；
- 没有匹配时返回空数组，并明确 `NO_HISTORY_MATCH` 提示，不返回虚构供应商；
- 有效黑名单对象不得作为推荐候选；白名单可用于提示或加分，但不能把历史关系变成强制关系。

当前历史检索、聚合、排序、来源单据和历史价格提示已实现。黑名单模块尚未建立前，测试数据库中不存在可生效的黑名单对象；名单模块实现后必须通过公开 `BlacklistServiceProtocol` 在本接口返回候选前完成过滤，Agent 不需要改变调用格式。

### 6.6 员工确认提交审批

`POST /api/v1/purchase-requirements/{requirement_id}/submit`

请求头必须包含新的 `Idempotency-Key`，不能复用创建或修改草稿时的键。

请求：

```json
{
  "version": 4,
  "confirmed": true,
  "recommendation_id": null
}
```

`recommendation_id` 可为空；为空表示员工没有采用系统推荐或没有推荐结果。采用推荐时，后端仍需以采购单当前的 `supplier_id` 和 `supplier_name` 为最终选择，不允许推荐记录暗中覆盖草稿。

响应 `200 OK`：

```json
{
  "data": {
    "requirement_id": 501,
    "requirement_no": "PR-20260721-0501",
    "status": "PENDING_APPROVAL",
    "version": 5,
    "submitted_at": "2026-07-21T06:45:00Z"
  },
  "meta": {
    "request_id": "req-20260721-003"
  }
}
```

提交校验：

- 当前用户是申请人本人；
- 当前状态为 `DRAFT`；
- `confirmed` 必须为 `true`；
- 当前版本与请求版本一致；
- 必填字段和品类模板字段完整；
- 数量、金额格式和范围合法；
- 商品、供应商为新增或非推荐项时生成明确提示/风险快照，但不因 `product_supplier` 无关系而直接失败；
- 有效黑名单命中时按项目规则阻断提交；
- 后端重新计算总价，保存申请人和业务字段快照；
- 在同一事务内写入提交时间、状态历史、推荐快照引用和审计记录。

### 6.7 取消草稿

`POST /api/v1/purchase-requirements/{requirement_id}/cancel`

请求：

```json
{
  "version": 4,
  "confirmed": true,
  "reason": "员工不再需要采购"
}
```

只允许申请人取消本人尚未进入审批的草稿。成功后返回 `CANCELLED` 和新版本号。

### 6.8 查询本人采购申请

`GET /api/v1/purchase-requirements?mine=true&status=DRAFT&page=1&page_size=20`

Agent 用于“继续上次草稿”或“查看我的采购状态”。响应为分页摘要，至少包含 `requirement_id`、`requirement_no`、商品名称、状态、总价、更新时间和版本。

## 7. 同进程 Service 契约

在当前模块化单体中，Agent Handler 不应自行发送 HTTP 请求绕回本应用，而应依赖由后端实现的公开 Service Protocol。方法语义与第 6 节 HTTP 接口一一对应：

```python
class RequirementServiceProtocol(Protocol):
    async def create_draft(
        self,
        command: CreateRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail: ...

    async def get_detail(
        self,
        requirement_id: int,
        scope: UserDataScope,
        actor: CurrentUser,
    ) -> RequirementDetail: ...

    async def update_draft(
        self,
        requirement_id: int,
        command: UpdateRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail: ...

    async def submit(
        self,
        requirement_id: int,
        command: SubmitRequirement,
        context: AuditContext,
    ) -> RequirementSubmissionResult: ...

    async def cancel_draft(
        self,
        requirement_id: int,
        command: CancelRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail: ...


class HistoricalSupplierRecommendationServiceProtocol(Protocol):
    async def search(
        self,
        query: HistoricalSupplierQuery,
        scope: UserDataScope,
        actor: CurrentUser,
    ) -> HistoricalSupplierRecommendationResult: ...
```

Agent 开发者依赖这些 Protocol 和 Pydantic Schema；后端开发者实现它们。Agent 模块不得引用 requirement、recommendation、product 或 supplier 模块的 Repository/ORM 类型。

## 8. Agent 的标准调用顺序

```text
员工描述采购需求
  -> Agent 提取已知字段
  -> create_draft（只调用一次）
  -> 后端返回 missing_fields/conflicts
  -> Agent 逐项追问
  -> update_draft（每次只提交变化字段）
  -> 商品信息足够后 search historical suppliers
  -> Agent 展示历史单据和历史供应商，仅供参考
  -> 员工选择推荐供应商或填写其他供应商
  -> update_draft 保存员工最终选择
  -> get_detail 读取数据库最新版本
  -> Agent 展示完整采购单和风险提示
  -> 员工明确确认提交审批
  -> submit
  -> 后端返回 PENDING_APPROVAL
  -> Agent 展示申请单号和当前状态
```

会话恢复时，Agent 使用保存的 `requirement_id` 调用 `get_detail`，以数据库内容覆盖过期的会话缓存。

## 9. Agent 对错误的处理

| HTTP/错误码 | 含义 | Agent 行为 |
| --- | --- | --- |
| 401 `UNAUTHENTICATED` | 没有有效登录身份 | 提示重新登录，不继续写入 |
| 403 `FORBIDDEN` | 无权读取或修改该申请 | 提示无权限，不猜测记录内容 |
| 404 `RESOURCE_NOT_FOUND` | 草稿或关联对象不存在 | 提示记录不存在或已不可访问 |
| 409 `STATE_CONFLICT` | 当前状态不允许该操作 | 重新获取详情并展示当前状态 |
| 409 `VERSION_CONFLICT` | 草稿被其他操作更新 | 重新获取详情，请员工核对差异 |
| 409 `IDEMPOTENCY_CONFLICT` | 同一幂等键用于不同请求 | 生成新键前先确认是不是新的用户操作 |
| 422 `VALIDATION_ERROR` | 字段格式或业务校验失败 | 按 `details.field` 针对性追问/纠正 |
| 422 `REQUIREMENT_INCOMPLETE` | 提交审批时必填项不足 | 按 `missing_fields` 继续补充，不重复创建草稿 |
| 422 `EMPLOYEE_NOT_MAPPED` | 登录用户未映射员工记录 | 提示联系管理员完善员工信息 |
| 422 `BLACKLIST_BLOCKED` | 命中有效黑名单 | 明确提示被阻断，不建议绕过 |
| 200 + `NO_HISTORY_MATCH` | 没有相似历史记录 | 告知“暂无历史参考”，允许继续填写新供应商 |

Agent 只能依赖 `error.code` 和结构化详情做程序判断，不得解析中文 `message` 决定流程。

## 10. 双方开发清单

### 10.1 Agent 开发者交付

- `RequirementDraft` 的结构化抽取 Schema；
- 创建/补充/纠正/确认/取消/状态查询的意图与阶段流转；
- `RequirementServiceProtocol` 和推荐 Service Protocol 的调用适配；
- `missing_fields`、`conflicts`、`warnings` 的对话呈现；
- 历史推荐卡片或文本展示，包含来源单号、日期、币种和“仅供参考”标识；
- 提交前完整确认页面/卡片及明确确认事件；
- 异常、超时和重新加载处理；
- 单元测试：缺失字段追问、员工改填新供应商、不采用推荐、未经确认不得提交、版本冲突恢复。

### 10.2 后端开发者交付

- 本文第 6 节 HTTP Router 和 Pydantic Schema；
- 本文第 7 节 Service Protocol 的实现；
- Requirement Repository、历史查询和推荐聚合查询；
- 身份到员工记录的映射与数据范围校验；
- 草稿状态机、乐观锁、幂等、事务和审计；
- 商品/供应商可空外键与文本快照处理；
- 历史推荐排序、来源引用、黑名单过滤和空结果；
- API/Service 测试：正常、参数异常、越权、非法状态、幂等、版本冲突和事务回滚。

### 10.3 联调共同验收

双方至少共同验证以下场景：

1. 员工只说“买两台服务器”时成功建立不完整草稿，Agent 继续追问。
2. 多轮补充始终修改同一 `requirement_id`，不会产生多张重复草稿。
3. 输入已有商品后能展示历史供应商及来源采购单。
4. 员工不采用推荐，填写数据库中不存在的新供应商，仍能保存草稿。
5. 员工未确认时，Agent 不调用 `submit`。
6. 员工确认后状态从 `DRAFT` 变为 `PENDING_APPROVAL`，并记录 `submitted_at`。
7. 并发修改导致版本冲突时，不覆盖另一端修改。
8. 没有历史记录时明确返回空推荐，Agent 不编造供应商或价格。
9. 命中有效黑名单时阻断正式提交。
10. 其他员工不能读取、修改或提交不属于自己的草稿。

## 11. 契约变更规则

- 新增可选字段属于兼容变更，可以在双方审查后加入 v1。
- 删除字段、修改字段含义、改变必填性、修改金额格式或状态语义属于不兼容变更，必须先更新本文并由双方确认。
- 不兼容变更原则上发布 `/api/v2`，不得让 Agent 与后端在未同步的情况下分别修改。
- 以仓库中已合入 `main` 的本文件版本为联调依据；聊天记录只用于讨论，不作为最终契约。

## 12. 聊天入口与 Agent 运行边界

- Router 只负责身份、Header、请求/响应 Schema 和分页参数，调用 `AgentChatService`。
- `AgentChatService` 负责编排会话锁、幂等、历史、意图、Agent 调用和结果保存。
- `GENERAL_QUERY` 不注册任何工具；采购意图只暴露既有受控采购工具。
- `AgentContext` 接收 Router 已验证的 `CurrentUser`，不得解析或持久化原始 Authorization。
- Anthropic 与 OpenAI 兼容客户端统一实现 `AgentModelProtocol`；Provider 只由服务端配置选择。
- Redis 保存最近 100 条短期消息，TTL 默认 7 天；模型最多回放最近 12 条成功消息。
- 同一会话串行、不同会话并行；失败的模型回复不进入后续上下文。
- 用户消息先记录为 `PROCESSING`，成功改为 `COMPLETED`，失败改为 `FAILED`。
- 生产环境 Redis 不可用时返回 `AGENT_UNAVAILABLE`；仅测试或显式本地模式允许内存实现。
- 会话重置只清除 Redis，不得删除、撤销或修改任何 MySQL 采购事实。
