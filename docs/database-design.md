# 数据库设计基线

## 1. 全局约束

- MySQL 8.0+、InnoDB、`utf8mb4`、`utf8mb4_0900_ai_ci`。
- 主键统一 `BIGINT UNSIGNED`；对外使用不可枚举的稳定业务编号，不以名称作为唯一标识。
- 时间以 UTC `DATETIME(6)` 存储；API 使用带时区的 ISO 8601。
- 金额使用 `DECIMAL(18,4)`，币种使用 ISO 4217 三字码；数量按物资精度使用 `DECIMAL(18,4)`。
- 重要表包含 `created_at`、`updated_at`、`created_by`、`updated_by`；并发聚合根包含 `version`。
- 逻辑失效使用 `status`/`is_active` 和生效区间；审批、名单、采购、交付、验收、入库和审计事实不得物理删除。
- JSON 仅保存可变规格、快照或模型结果，不替代可查询的核心关系字段。
- 所有外键、唯一约束和高频组合索引必须在迁移中显式声明。

## 2. 表域

| 域 | 表 | M1/M2 状态 |
| --- | --- | --- |
| 系统/权限 | `sys_user`、`sys_role`、`sys_user_role`、`sys_organization`、`sys_user_data_scope` | Planned M2 |
| 主数据 | `md_product_category`、`md_product`、`md_supplier`、`md_product_supplier`、`md_product_replacement` | 前四项 Planned M2；替代 M4 |
| 白名单 | `wl_product_whitelist`、`wl_whitelist_history` | Planned M2 |
| 黑名单 | `bl_procurement_blacklist`、`bl_blacklist_review`、`bl_blacklist_history` | Planned M2 |
| 历史采购 | `hp_purchase_record`、`hp_price_record` | Planned M2 |
| 需求 | `pr_requirement`、`pr_requirement_item`、`pr_status_history`、`pr_attachment` | M3/M4 |
| 审批 | `ap_approval_instance`、`ap_approval_task`、`ap_approval_record` | M4 |
| 采购 | `po_purchase_order`、`po_purchase_order_item`、`po_quotation` | M5 |
| 交付 | `dl_delivery_event` | M5 |
| 验收入库 | `qa_inspection_record`、`qa_inspection_item`、`wh_inbound_order`、`wh_inbound_item` | M5 |
| Agent | `ag_conversation`、`ag_message`、`ag_extraction_record`、`ag_recommendation_snapshot`、`ag_model_call_log` | M3/M4 |
| 审计任务 | `au_operation_log`、`task_system_task`、`api_idempotency_record` | M1/M2 |

## 3. M1/M2 核心模型

### 3.1 身份和数据范围

- `sys_user(user_code, display_name, organization_id, status, external_identity)`；`user_code` 唯一。
- `sys_role(role_code, role_name, status)`；`role_code` 唯一。
- `sys_user_role(user_id, role_id, valid_from, valid_to)`；用户、角色和有效期组合唯一。
- `sys_organization(org_code, name, org_type, parent_id, status)`；树结构，楼宇以 `org_type=BUILDING` 表示。
- `sys_user_data_scope(user_id, scope_type, scope_object_id, valid_from, valid_to)`；支持本人、组织、楼宇和全局范围。

自审禁令由 ApprovalService 根据申请人与当前用户比较执行，不只依赖角色。

### 3.2 产品和供应商

- `md_product_category(category_code, name, parent_id, required_fields_schema, status, version)`。
- `md_product(product_code, category_id, name, brand, model, series, specifications, lifecycle_status, discontinued_at, status, version)`。
- 产品业务唯一键为规范化后的 `(brand, model)`；型号未知时必须使用受控临时编码并待清洗。
- `md_supplier(supplier_code, legal_name, short_name, status, contact_summary, version)`；`supplier_code` 和法定名称分别唯一。
- `md_product_supplier(product_id, supplier_id, supplier_sku, cooperation_status, lead_time_days, valid_from, valid_to, version)`；有效关系组合唯一。

生命周期枚举：`IN_PRODUCTION`、`PHASING_OUT`、`DISCONTINUED`、`DELISTED`、`OUT_OF_STOCK`、`UNKNOWN`。

### 3.3 白名单

`wl_product_whitelist` 关键字段：

- `whitelist_no`、`object_type`、`object_id`、可选 `supplier_id`；
- `organization_id`/`building_id`/`category_id` 适用范围；
- `source`、`approval_reference`、`valid_from`、`valid_to`、`status`、`version`；
- `object_type` 支持 PRODUCT、MODEL、SERIES、BRAND、SUPPLIER、PRODUCT_SUPPLIER。

查询“当前有效”必须同时满足状态 ACTIVE、生效时间不晚于当前时刻、失效时间为空或晚于当前时刻，以及调用人的数据范围。版本变化追加 `wl_whitelist_history`，不得覆盖来源和依据。

### 3.4 黑名单

`bl_procurement_blacklist` 关键字段：

- `blacklist_no`、`object_type`、`object_id`、可选 `supplier_id`；
- `reason`、`issue_type`、`severity`、范围、生效/失效时间、`release_condition`；
- `evidence_refs`、`related_purchase_order_id`、`status`、`initiator_id`、`reviewed_by`、`version`。

状态：`DRAFT`、`PENDING_REVIEW`、`ACTIVE`、`REJECTED`、`EXPIRED`、`RELEASED`。发起人与复核人不得相同；缩短或解除只能由采购管理员执行并追加 `bl_blacklist_review` 和 `bl_blacklist_history`。MVP 不建黑名单例外表。

### 3.5 历史采购和价格

- `hp_purchase_record(source_system, source_record_key, organization_id, building_id, product_id, supplier_id, quantity, ordered_at, promised_at, delivered_at, quality_result)`。
- `hp_price_record(purchase_record_id, unit_price, currency, tax_included, tax_rate, freight, price_date)`。
- `(source_system, source_record_key)` 唯一，重复导入返回原记录。
- 价格展示必须连同日期、币种、税费口径和数量；禁止将金额转为浮点数。

### 3.6 审计、幂等和任务

- `au_operation_log(actor_id, actor_role, action, object_type, object_id, occurred_at, before_value, after_value, reason, request_id, idempotency_key, source_ip, result)`；只追加。
- `api_idempotency_record(scope, idempotency_key, request_hash, response_status, response_body, resource_type, resource_id, expires_at)`；`(scope, idempotency_key)` 唯一。
- `task_system_task(task_type, business_key, payload, status, run_at, attempts, max_attempts, locked_by, locked_until, last_error)`；`(task_type, business_key)` 按任务语义唯一。

## 4. 后续聚合约束

- 需求单号、采购单号、入库单号均唯一且不可复用。
- 状态历史、审批记录和交付事件只追加；当前状态作为聚合根的可查询投影。
- 一个已批准需求只能创建一个活动采购任务；重复创建由唯一约束和幂等记录共同阻断。
- 入库单业务唯一键包含订单、到货批次和外部请求号；累计合格入库数量不得超过订单明细数量。
- 推荐快照保存候选、过滤原因、评分分解、规则/权重版本、数据引用和时间，不依赖后续主数据状态还原。

## 5. 索引基线

- 所有外键列建立索引。
- 名单查询：`(status, valid_from, valid_to, object_type, object_id)`，并为组织/楼宇/品类范围建立组合索引。
- 产品检索：分类、品牌、型号、生命周期和状态组合索引；文本搜索策略在 M2 Issue 中用真实数据验证。
- 历史查询：`(product_id, supplier_id, ordered_at)`、`(organization_id, category_id, ordered_at)`。
- 审计：`(object_type, object_id, occurred_at)`、`(actor_id, occurred_at)`、`request_id`。
- 任务：`(status, run_at)`、`locked_until`。

索引必须以实际查询和 `EXPLAIN` 验证；不得为每列机械建索引。

## 6. 迁移规范

1. 从最新 `main` 创建任务分支，执行 `alembic heads`，只允许一个 head。
2. 检查自动生成迁移的类型、默认值、索引、唯一约束、外键和 downgrade。
3. 新增非空字段采用“可空/默认 -> 回填 -> 非空”分阶段迁移。
4. 从空测试库执行 `alembic upgrade head`；高风险迁移同时验证 downgrade 或书面说明不可逆原因。
5. 已合入迁移不可修改，修正必须新增迁移。
6. PR 明确表、字段、数据兼容、锁表风险和回滚路径。

## 7. 数据保留

- 审计、审批、名单、状态、采购、交付和入库历史默认保留三年，正式保留期变更由合规决策记录管理。
- 模型调用日志只保留完成审计和评估所需的脱敏内容，并设置更短的可配置生命周期。
- 删除用户展示数据时不得破坏法定业务与审计关联；采用匿名化或受控失效。
